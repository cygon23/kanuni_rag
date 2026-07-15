"""Post-deploy smoke test (§12): /readyz, then one canned query asserting a citation.

Run by .github/workflows/deploy.yml against staging (and, if desired,
prod) right after each deploy — no test framework, just a script that
exits non-zero on failure so the workflow step fails loudly.

The citation assertion requires the target environment's corpus to
already have at least one document ingested covering the canned
question below — on a brand-new environment, ingest the fixture corpus
(or a real one) before this will pass; see docs/runbook.md.
"""

import argparse
import json
import urllib.error
import urllib.request

_CANNED_QUESTION = "What is the minimum core capital requirement for a bank in Tanzania?"
_TIMEOUT_SECONDS = 30


def _check_readyz(base_url: str) -> None:
    request = urllib.request.Request(f"{base_url}/readyz")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        print(f"FAIL: /readyz returned HTTP {exc.code}: {exc.read().decode(errors='replace')}")
        raise SystemExit(1) from exc
    if body.get("status") != "ok":
        print(f"FAIL: /readyz reported not ready: {body}")
        raise SystemExit(1)
    print("OK: /readyz")


def _check_canned_query(base_url: str, api_key: str) -> None:
    payload = json.dumps(
        {"question": _CANNED_QUESTION, "include_historical": False, "top_k": None}
    ).encode()
    request = urllib.request.Request(
        f"{base_url}/v1/query",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"FAIL: POST /v1/query returned HTTP {exc.code}: {detail}")
        raise SystemExit(1) from exc

    done_data = None
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "event: done" and i + 1 < len(lines):
            done_data = json.loads(lines[i + 1].removeprefix("data: "))
            break

    if done_data is None:
        print(f"FAIL: no 'done' event in the SSE response:\n{raw[:2000]}")
        raise SystemExit(1)
    if not done_data.get("answered"):
        print(
            f"FAIL: canned query was refused (confidence={done_data.get('confidence')!r}) — "
            "has the corpus been ingested in this environment? See docs/runbook.md."
        )
        raise SystemExit(1)
    if not done_data.get("citations"):
        print(f"FAIL: answered but returned zero citations: {done_data}")
        raise SystemExit(1)
    print(f"OK: POST /v1/query returned {len(done_data['citations'])} citation(s)")


def main() -> None:
    """Run the smoke test against the given base URL and API key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="e.g. https://kanuni-api-staging.fly.dev")
    parser.add_argument("--api-key", required=True, help="a query-scoped Kanuni API key")
    args = parser.parse_args()

    _check_readyz(args.base_url)
    _check_canned_query(args.base_url, args.api_key)


if __name__ == "__main__":
    main()
