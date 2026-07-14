"""Tests for the `kanuni ingest` CLI: validation, manifest matching, and upload handling.

Per PROJECT_SPEC.md §13, no test may call a real network service — the
admin API is mocked via `pytest-httpx`'s `httpx_mock` fixture.
"""

from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from kanuni_ingest.cli import _build_metadata, _load_manifest, _validate_pdf, app

runner = CliRunner()


def test_validate_pdf_accepts_a_real_pdf(fixtures_dir: Path) -> None:
    """A genuine PDF fixture should pass validation."""
    error = _validate_pdf(fixtures_dir / "bot-2014-licensing.pdf")

    assert error is None


def test_validate_pdf_rejects_non_pdf_extension(tmp_path: Path) -> None:
    """A file that isn't named .pdf should be rejected regardless of content."""
    text_file = tmp_path / "not-a-pdf.txt"
    text_file.write_bytes(b"%PDF-1.4\nirrelevant")

    assert _validate_pdf(text_file) == "not a .pdf file"


def test_validate_pdf_rejects_empty_file(tmp_path: Path) -> None:
    """A zero-byte file should be rejected."""
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")

    assert _validate_pdf(empty_file) == "file is empty"


def test_validate_pdf_rejects_missing_magic_bytes(tmp_path: Path) -> None:
    """A .pdf-named file without the %PDF- header should be rejected."""
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not actually a pdf file at all")

    assert _validate_pdf(fake_pdf) == "file does not have a PDF magic-byte header"


def test_load_manifest_reads_entries_for_the_given_source(tmp_path: Path) -> None:
    """Manifest entries should load correctly for the requested source id only."""
    manifest_path = tmp_path / "sources.yaml"
    manifest_path.write_text(
        """
sources:
  bot:
    name: "Bank of Tanzania"
    issuing_body: "Bank of Tanzania"
    jurisdiction: "Tanzania"
    documents:
      - filename: bot-2014-licensing.pdf
        title: "The Licensing Regulations, 2014"
        doc_type: regulation
        language: en
        reference_number: "G.N. No. 297"
        issued_date: "2014-08-22"
  other:
    name: "Other Source"
    issuing_body: "Other Body"
    jurisdiction: "Other"
    documents:
      - filename: other-doc.pdf
        title: "Should not appear"
        doc_type: notice
        language: en
"""
    )

    entries = _load_manifest(manifest_path, "bot")

    assert set(entries) == {"bot-2014-licensing.pdf"}
    assert entries["bot-2014-licensing.pdf"].reference_number == "G.N. No. 297"


def test_build_metadata_uses_manifest_entry_when_present(tmp_path: Path) -> None:
    """A file matching a manifest entry should use its declared metadata."""
    manifest_path = tmp_path / "sources.yaml"
    manifest_path.write_text(
        """
sources:
  bot:
    name: "Bank of Tanzania"
    issuing_body: "Bank of Tanzania"
    jurisdiction: "Tanzania"
    documents:
      - filename: known.pdf
        title: "Known Document"
        doc_type: circular
        language: sw
        reference_number: "G.N. No. 1"
        issued_date: "2020-01-01"
"""
    )
    entries = _load_manifest(manifest_path, "bot")

    metadata = _build_metadata(Path("known.pdf"), "bot", entries)

    assert metadata == {
        "source_id": "bot",
        "title": "Known Document",
        "doc_type": "circular",
        "language": "sw",
        "reference_number": "G.N. No. 1",
        "issued_date": "2020-01-01",
    }


def test_build_metadata_falls_back_to_defaults_when_unmatched() -> None:
    """A file with no manifest entry should still get reasonable defaults."""
    metadata = _build_metadata(Path("unlisted-document.pdf"), "bot", {})

    assert metadata == {
        "source_id": "bot",
        "title": "unlisted-document",
        "doc_type": "regulation",
        "language": "en",
    }


def test_ingest_reports_created_skipped_and_failed(
    httpx_mock: HTTPXMock, fixtures_dir: Path, tmp_path: Path
) -> None:
    """The CLI should classify each file as ingested, skipped, or failed, and exit accordingly."""
    folder = tmp_path / "batch"
    folder.mkdir()
    (folder / "good.pdf").write_bytes((fixtures_dir / "bot-2014-licensing.pdf").read_bytes())
    (folder / "duplicate.pdf").write_bytes(
        (fixtures_dir / "bot-2015-electronic-money.pdf").read_bytes()
    )
    (folder / "broken.pdf").write_bytes(b"not a pdf")

    # Files are visited in sorted order: broken.pdf (fails validation, no HTTP
    # call), then duplicate.pdf, then good.pdf — responses are queued to match.
    httpx_mock.add_response(
        url="http://admin.example/v1/admin/documents",
        method="POST",
        status_code=200,
        json={"status": "skipped", "document_id": "22222222-2222-2222-2222-222222222222"},
    )
    httpx_mock.add_response(
        url="http://admin.example/v1/admin/documents",
        method="POST",
        status_code=201,
        json={"status": "created", "document_id": "11111111-1111-1111-1111-111111111111"},
    )

    result = runner.invoke(
        app,
        [
            "ingest",
            str(folder),
            "--source",
            "bot",
            "--api-base-url",
            "http://admin.example",
            "--api-key",
            "test-admin-key",
        ],
    )

    assert "ingested" in result.output
    assert "skipped" in result.output
    assert "failed" in result.output
    assert result.exit_code == 1


@pytest.mark.parametrize("status_code", [500, 503])
def test_upload_failure_status_codes_are_reported_as_failed(
    httpx_mock: HTTPXMock, fixtures_dir: Path, tmp_path: Path, status_code: int
) -> None:
    """A non-200/201 admin API response should be reported as a failed upload."""
    folder = tmp_path / "batch"
    folder.mkdir()
    (folder / "doc.pdf").write_bytes((fixtures_dir / "bot-2014-licensing.pdf").read_bytes())
    httpx_mock.add_response(
        url="http://admin.example/v1/admin/documents",
        method="POST",
        status_code=status_code,
        text="server error",
    )

    result = runner.invoke(
        app,
        [
            "ingest",
            str(folder),
            "--source",
            "bot",
            "--api-base-url",
            "http://admin.example",
            "--api-key",
            "test-admin-key",
        ],
    )

    assert "failed" in result.output
    assert result.exit_code == 1
