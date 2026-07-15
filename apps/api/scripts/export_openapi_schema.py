"""Exports the Kanuni API's OpenAPI schema to a file, without needing a running server.

`create_app()` registers every route/pydantic model at import time; the
OpenAPI schema is derived purely from that route table, so this needs no
database connection or live process — `make openapi` runs it directly,
feeding the result to `openapi-typescript` for `packages/shared`.
"""

import json
import sys
from pathlib import Path

from kanuni_api.main import create_app


def main() -> None:
    """Write the API's OpenAPI schema as JSON to the path given as argv[1]."""
    if len(sys.argv) != 2:
        print("usage: export_openapi_schema.py <output-path>", file=sys.stderr)
        raise SystemExit(1)

    output_path = Path(sys.argv[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    output_path.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"Wrote OpenAPI schema to {output_path}")


if __name__ == "__main__":
    main()
