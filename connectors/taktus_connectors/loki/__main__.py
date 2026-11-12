"""Run the log store connector as a process.

    uv run python -m taktus_connectors.loki --port 9131 --target https://loki.example

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address and is required: the store is self-hosted or a tenant's own cloud address, so
there is no default. Point it at the fake under `tests/fakes/log_store_service.py` to run
without a network. `--tenant` names the tenant of a multi-tenant store, sent as
`X-Scope-OrgID`. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.loki.operations import Config
from taktus_connectors.loki.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The log store connector.", 9131)
    parser.add_argument("--target", default="", help="the API's address (required)")
    parser.add_argument("--tenant", default=None, help="the tenant, sent as X-Scope-OrgID")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required")
    config = Config(args.target, args.tenant, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
