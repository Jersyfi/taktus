"""Run the workspace audit connector as a process.

    uv run python -m taktus_connectors.googleworkspace --port 9153 --subject admin@org.example

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address and `--token-url` the token endpoint (default the service's own); point both at
the fake under `tests/fakes/workspace_reports_service.py` to run without a network.
`--subject` is the administrator the service account acts for. Credentials are never
arguments: the connector reads the service account's key file at the moment of a call, from the
file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.googleworkspace.operations import TARGET, TOKEN_URL, Config
from taktus_connectors.googleworkspace.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The workspace audit connector.", 9153)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--token-url", default=TOKEN_URL, help="the token endpoint")
    parser.add_argument("--subject", default="", help="the administrator acted for (required)")
    args = parser.parse_args(argv)
    if not args.subject and not args.list_faults:
        parser.error("--subject is required")
    config = Config(args.target, args.subject, args.token_url, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
