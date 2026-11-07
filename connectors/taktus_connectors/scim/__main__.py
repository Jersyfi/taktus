"""Run the directory connector as a process.

    uv run python -m taktus_connectors.scim --port 9151 --target https://idp.example/scim/v2

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
SCIM service's base address, the one under which `/Users` and `/Groups` are found; point it at
the fake under `tests/fakes/directory_service.py` to run without a network. Credentials are
never arguments: the connector reads the value of a credential at the moment of a call, from
the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.scim.operations import Config
from taktus_connectors.scim.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The directory connector.", 9151)
    parser.add_argument("--target", default="", help="the SCIM service's base address (required)")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required: SCIM has no address of its own")
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
