"""Run the check connector as a process.

    uv run python -m taktus_connectors.httpcheck --port 9105 \
        --target https://service.example

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
base address of the service the checks are made against. Credentials are never arguments: the
connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.httpcheck.operations import Config
from taktus_connectors.httpcheck.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The check connector.", 9105)
    parser.add_argument("--target", default="http://127.0.0.1:8080", help="the service's address")
    args = parser.parse_args(argv)
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
