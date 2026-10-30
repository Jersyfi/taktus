"""Run the model costs connector over the cost report as a process.

    uv run python -m taktus.adapters.driven.connectors.anthropic --port 9112

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default the provider's own); point it at the fake under
`tests/fakes/cost_report_service.py` to run without a network. Credentials are never arguments:
the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus.adapters.driven.connectors import serving
from taktus.adapters.driven.connectors.anthropic.operations import TARGET, Config
from taktus.adapters.driven.connectors.anthropic.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The model costs connector over the cost report.", 9112)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    args = parser.parse_args(argv)
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
