"""Run the product analytics connector as a process.

    uv run python -m taktus_connectors.mixpanel --port 9182 --project 1234567

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://mixpanel.com` unless given (`https://eu.mixpanel.com` or
`https://in.mixpanel.com` for a project enrolled in data residency); point it at the fake under
`tests/fakes/product_analytics_service.py` to run without the service. `--project` is the
numeric identifier of the one project whose figures are read, `--workspace` the identifier of
its global data view where the project has data views. Credentials are never arguments: the
connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.mixpanel.operations import TARGET, Config
from taktus_connectors.mixpanel.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The product analytics connector.", 9182)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--project", default="", help="the project's numeric id (required)")
    parser.add_argument("--workspace", default="", help="the global data view's id, if any")
    args = parser.parse_args(argv)
    if not args.project and not args.list_faults:
        parser.error("--project is required")
    config = Config(args.target, args.project, args.workspace, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
