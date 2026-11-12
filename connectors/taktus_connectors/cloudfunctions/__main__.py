"""Run the functions connector as a process.

    uv run python -m taktus_connectors.cloudfunctions --port 9184 \
        --project shop-prod --location europe-west1

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://cloudfunctions.googleapis.com` unless given; point it at the fake under
`tests/fakes/functions_service.py` to run without the service. `--project` and `--location`
name where the functions are. Credentials are never arguments: the connector reads the value of
a credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.cloudfunctions.operations import TARGET, Config
from taktus_connectors.cloudfunctions.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The functions connector.", 9184)
    parser.add_argument("--target", default=TARGET, help="the API")
    parser.add_argument("--project", default="", help="the project (required)")
    parser.add_argument("--location", default="", help="the location (required)")
    parser.add_argument("--token-endpoint", default="", help="where the key is exchanged")
    args = parser.parse_args(argv)
    if not (args.project and args.location) and not args.list_faults:
        parser.error("--project and --location are required")
    config = Config(args.target, args.project, args.location, args.timeout, args.token_endpoint)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
