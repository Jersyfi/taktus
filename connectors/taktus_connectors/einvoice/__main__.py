"""Run the documents connector as a process.

    uv run python -m taktus_connectors.einvoice --target https://files.example/inbox/ --port 9113

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
inbox folder's WebDAV address; point it at the fake under `tests/fakes/document_inbox_service.py`
to run without a network. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.einvoice.operations import Config
from taktus_connectors.einvoice.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The documents connector.", 9113)
    parser.add_argument("--target", default="", help="the inbox folder's WebDAV address")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required: the inbox folder's WebDAV address")
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
