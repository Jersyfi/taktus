"""Run the social mentions connector as a process.

    uv run python -m taktus_connectors.mastodon --target https://social.example --port 9149

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
address of the server searched, which has no default: every server is its own; point it at the
fake under `tests/fakes/social_service.py` to run without a network. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.mastodon.operations import Config
from taktus_connectors.mastodon.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The social mentions connector.", 9149)
    parser.add_argument("--target", default="", help="the address of the server searched")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required: the address has no default")
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
