"""Run the error tracking connector as a process.

    uv run python -m taktus_connectors.sentry --port 9110 --organization acme

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default the provider's own); point it at the fake under
`tests/fakes/error_tracking_service.py` to run without a network. `--organization` is the slug
of the organisation whose issues are read. Credentials are never arguments: the connector reads
the value of a credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE`
names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.sentry.operations import TARGET, Config
from taktus_connectors.sentry.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The error tracking connector.", 9110)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--organization", default="", help="the organisation's slug (required)")
    args = parser.parse_args(argv)
    if not args.organization and not args.list_faults:
        parser.error("--organization is required")
    config = Config(args.target, args.organization, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
