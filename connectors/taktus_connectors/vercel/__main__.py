"""Run the site connector as a process.

    uv run python -m taktus_connectors.vercel --port 9134 --team team_example

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.vercel.com` unless given; point it at the fake under
`tests/fakes/site_deployments_service.py` to run without the platform. `--team` is the team's
identifier every request is made on behalf of, as the API's `teamId`; without it, the token's
own account. Credentials are never arguments: the connector reads the value of a credential at
the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the
call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.vercel.operations import TARGET, Config
from taktus_connectors.vercel.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The site connector.", 9134)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--team", default=None, help="the team's identifier (teamId)")
    args = parser.parse_args(argv)
    config = Config(args.target, args.team, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
