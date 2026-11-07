"""Run the site connector as a process.

    uv run python -m taktus_connectors.firebase --port 9132

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://firebasehosting.googleapis.com` unless given; point it at the fake under
`tests/fakes/hosting_releases_service.py` to run without the service. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.firebase.operations import TARGET, Config
from taktus_connectors.firebase.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The site connector.", 9132)
    parser.add_argument("--target", default=TARGET, help="the API")
    parser.add_argument("--token-endpoint", default="", help="where the key is exchanged")
    args = parser.parse_args(argv)
    config = Config(args.target, args.timeout, args.token_endpoint)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
