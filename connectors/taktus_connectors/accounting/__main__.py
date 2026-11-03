"""Run the accounting connector as a process.

    uv run python -m taktus_connectors.accounting --target https://books.example/v1 --port 9114

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
address of the accounting interface (`README.md`); point it at the fake under
`tests/fakes/accounting_service.py` to run without a network. Credentials are never arguments:
the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references.
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.accounting.operations import Config
from taktus_connectors.accounting.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The accounting connector.", 9114)
    parser.add_argument("--target", default="", help="the accounting interface's address")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required: the accounting interface's address")
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
