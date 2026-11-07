"""Run the in-app subscription connector as a process.

    uv run python -m taktus_connectors.revenuecat --port 9145 --project proj1ab2c3d4

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default the provider's own); point it at the fake under
`tests/fakes/app_subscriptions_service.py` to run without a network. `--project` is the project
whose customers are read. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.revenuecat.operations import PROJECT, TARGET, Config
from taktus_connectors.revenuecat.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The in-app subscription connector.", 9145)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--project", default="", help="the project's identifier (required)")
    args = parser.parse_args(argv)
    if not args.list_faults and PROJECT.match(args.project) is None:
        parser.error("--project is required: the project's identifier")
    config = Config(args.target, args.project, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
