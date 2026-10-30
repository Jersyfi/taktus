"""Run the cloud billing connector as a process.

    uv run python -m taktus_connectors.aws --port 9108

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default the provider's own); point it at the fake under
`tests/fakes/cloud_billing_service.py` to run without a network. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.aws.operations import REGION, TARGET, Config
from taktus_connectors.aws.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The cloud billing connector.", 9108)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--region", default=REGION, help="the region requests are signed for")
    args = parser.parse_args(argv)
    config = Config(args.target, args.region, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
