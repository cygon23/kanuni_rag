"""Bulk ingestion CLI (`kanuni ingest`): a pure client of the admin upload API.

Per PROJECT_SPEC.md §7: walks a folder for PDFs, validates each, matches
against `sources.yaml` manifest entries when provided, and uploads via the
admin API — this module never touches the database or storage directly.
Already-ingested files (matching SHA-256, checked server-side) are reported
as skipped, making the command safely re-runnable.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import httpx
import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Kanuni bulk ingestion CLI.")
console = Console()

_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
_PDF_MAGIC_BYTES = b"%PDF-"


@app.callback()
def _main() -> None:
    """Kanuni bulk ingestion CLI — invoked as `kanuni ingest <folder> --source <source_id>`.

    A Typer app with exactly one command collapses into that command
    directly (losing the `ingest` subcommand name) unless it has a
    callback — this one exists solely to keep `ingest` an explicit
    subcommand, matching PROJECT_SPEC.md §7's literal invocation form.
    """


_DEFAULT_DOC_TYPE = "regulation"
_DEFAULT_LANGUAGE = "en"


@dataclass
class ManifestEntry:
    """A `sources.yaml` manifest entry for one document."""

    filename: str
    title: str
    doc_type: str
    language: str
    reference_number: str | None
    issued_date: str | None


@dataclass
class UploadResult:
    """The outcome of attempting to upload one file."""

    filename: str
    status: str
    detail: str


def _load_manifest(manifest_path: Path, source_id: str) -> dict[str, ManifestEntry]:
    """Load manifest entries for one source from a `sources.yaml`-shaped file.

    Args:
        manifest_path: Path to the manifest YAML file.
        source_id: The source whose `documents` entries should be loaded.

    Returns:
        A mapping of filename to manifest entry.
    """
    raw = yaml.safe_load(manifest_path.read_text())
    source = raw.get("sources", {}).get(source_id, {})
    entries: dict[str, ManifestEntry] = {}
    for document in source.get("documents", []):
        entries[document["filename"]] = ManifestEntry(
            filename=document["filename"],
            title=document.get("title", Path(document["filename"]).stem),
            doc_type=document.get("doc_type", _DEFAULT_DOC_TYPE),
            language=document.get("language", _DEFAULT_LANGUAGE),
            reference_number=document.get("reference_number"),
            issued_date=document.get("issued_date"),
        )
    return entries


def _validate_pdf(path: Path) -> str | None:
    """Validate a candidate file is a plausible, size-bounded PDF.

    Args:
        path: The candidate file path.

    Returns:
        An error message if invalid, or `None` if the file passes validation.
    """
    if path.suffix.lower() != ".pdf":
        return "not a .pdf file"
    size = path.stat().st_size
    if size == 0:
        return "file is empty"
    if size > _MAX_FILE_SIZE_BYTES:
        return f"file exceeds max size ({_MAX_FILE_SIZE_BYTES} bytes)"
    with path.open("rb") as handle:
        header = handle.read(len(_PDF_MAGIC_BYTES))
    if header != _PDF_MAGIC_BYTES:
        return "file does not have a PDF magic-byte header"
    return None


def _build_metadata(
    path: Path, source_id: str, manifest: dict[str, ManifestEntry]
) -> dict[str, str]:
    """Build the upload form metadata for one file, from its manifest entry if present.

    Args:
        path: The file being uploaded.
        source_id: The source this file belongs to.
        manifest: Manifest entries for this source, keyed by filename.

    Returns:
        Form fields to send alongside the file to the admin upload endpoint.
    """
    entry = manifest.get(path.name)
    fields = {
        "source_id": source_id,
        "title": entry.title if entry else path.stem,
        "doc_type": entry.doc_type if entry else _DEFAULT_DOC_TYPE,
        "language": entry.language if entry else _DEFAULT_LANGUAGE,
    }
    if entry and entry.reference_number:
        fields["reference_number"] = entry.reference_number
    if entry and entry.issued_date:
        fields["issued_date"] = entry.issued_date
    return fields


def _upload_file(
    client: httpx.Client, base_url: str, api_key: str, path: Path, metadata: dict[str, str]
) -> UploadResult:
    """Upload one file to the admin upload endpoint.

    Args:
        client: An HTTP client to reuse across uploads.
        base_url: The admin API base URL.
        api_key: The admin API key (scope `ingest:admin`).
        path: The file to upload.
        metadata: Form fields describing the document.

    Returns:
        The upload outcome.
    """
    with path.open("rb") as handle:
        response = client.post(
            f"{base_url}/v1/admin/documents",
            headers={"X-API-Key": api_key},
            data=metadata,
            files={"file": (path.name, handle, "application/pdf")},
        )

    if response.status_code == 201:
        body = response.json()
        return UploadResult(path.name, "ingested", str(body.get("document_id", "")))
    if response.status_code == 200:
        body = response.json()
        return UploadResult(path.name, "skipped", f"duplicate of {body.get('document_id', '')}")
    return UploadResult(path.name, "failed", f"HTTP {response.status_code}: {response.text[:200]}")


@app.command()
def ingest(
    folder: Annotated[Path, typer.Argument(help="Folder to walk for PDF files.")],
    source: Annotated[str, typer.Option("--source", help="Source id, per sources.yaml.")],
    manifest: Annotated[
        Path | None, typer.Option("--manifest", help="Path to a sources.yaml-shaped manifest.")
    ] = None,
    api_base_url: Annotated[
        str, typer.Option(envvar="KANUNI_ADMIN_API_BASE_URL")
    ] = "http://localhost:8000",
    api_key: Annotated[str, typer.Option(envvar="KANUNI_ADMIN_API_KEY")] = "",
) -> None:
    """Walk FOLDER for PDFs and upload them via the admin API under SOURCE."""
    manifest_entries = _load_manifest(manifest, source) if manifest and manifest.exists() else {}
    pdf_paths = sorted(folder.rglob("*.pdf"))

    results: list[UploadResult] = []
    with httpx.Client(timeout=60.0) as client:
        for path in pdf_paths:
            error = _validate_pdf(path)
            if error is not None:
                results.append(UploadResult(path.name, "failed", error))
                continue
            metadata = _build_metadata(path, source, manifest_entries)
            results.append(_upload_file(client, api_base_url, api_key, path, metadata))

    table = Table(title=f"kanuni ingest — {folder}")
    table.add_column("File")
    table.add_column("Status")
    table.add_column("Detail")
    for result in results:
        style = {"ingested": "green", "skipped": "yellow", "failed": "red"}[result.status]
        table.add_row(result.filename, f"[{style}]{result.status}[/{style}]", result.detail)
    console.print(table)

    if any(result.status == "failed" for result in results):
        sys.exit(1)


if __name__ == "__main__":
    app()
