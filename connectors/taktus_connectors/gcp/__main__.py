"""Run the cloud operations connector as a process.

    uv run python -m taktus_connectors.gcp --port 9140 --project acme-prod \
        --billing-table acme-billing.export.gcp_billing_export_v1_000000_000000_000000

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--project` names
the project whose logs and secrets are read and in which the cost query runs. `--target` puts
every API and the token endpoint (`<target>/token`) at one address, the fake's under
`tests/fakes/cloud_service.py` to run without a network; `--logging-target`,
`--bigquery-target`, `--secrets-target` and `--token-endpoint` override one each. Credentials
are never arguments: the connector reads the value of a credential at the moment of a call,
from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references
(`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.gcp.api import Config
from taktus_connectors.gcp.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The cloud operations connector.", 9140)
    parser.add_argument("--project", default="", help="the project's identifier (required)")
    parser.add_argument("--billing-table", default="", help="project.dataset.table of the export")
    parser.add_argument("--target", default=None, help="one address for every API and the token")
    parser.add_argument("--logging-target", default=None, help="the logging API's address")
    parser.add_argument("--bigquery-target", default=None, help="the query API's address")
    parser.add_argument("--secrets-target", default=None, help="the secret API's address")
    parser.add_argument("--token-endpoint", default=None, help="where a key is exchanged")
    args = parser.parse_args(argv)
    if not args.project and not args.list_faults:
        parser.error("--project is required")
    config = Config.at(
        args.project,
        args.billing_table,
        args.timeout,
        args.target,
        logging=args.logging_target,
        bigquery=args.bigquery_target,
        secrets=args.secrets_target,
        token_endpoint=args.token_endpoint,
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
