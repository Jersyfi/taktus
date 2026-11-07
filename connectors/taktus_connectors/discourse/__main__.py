"""Run the forum mentions connector as a process.

    uv run python -m taktus_connectors.discourse --target https://forum.example --port 9150

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
forum's address, which has no default; point it at the fake under `tests/fakes/forum_service.py`
to run without a network. `--username` is the forum user the key acts as (`system` by default),
which is configuration, not a secret. Credentials are never arguments: the connector reads the
value of a credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE`
names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.discourse.operations import Config
from taktus_connectors.discourse.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The forum mentions connector.", 9150)
    parser.add_argument("--target", default="", help="the forum's address")
    parser.add_argument("--username", default="system", help="the user the key acts as")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required: the address has no default")
    config = Config(args.target, args.username, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
