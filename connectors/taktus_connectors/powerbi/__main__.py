"""Run the business-intelligence connector as a process.

    uv run python -m taktus_connectors.powerbi --port 9157 --tenant example.onmicrosoft.com

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address and `--login` the identity platform's (default the provider's own); point both at
the fake under `tests/fakes/business_intelligence_service.py` to run without a network.
`--tenant` is the directory tenant the application is registered in. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.powerbi.operations import LOGIN, TARGET, Config
from taktus_connectors.powerbi.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The business-intelligence connector.", 9157)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--login", default=LOGIN, help="the identity platform's address")
    parser.add_argument("--tenant", default="", help="the directory tenant (required)")
    args = parser.parse_args(argv)
    if not args.tenant and not args.list_faults:
        parser.error("--tenant is required")
    config = Config(args.target, args.login, args.tenant, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
