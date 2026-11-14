"""Run the cloud operations connector as a process.

    uv run python -m taktus_connectors.gcp --port 9140 --project acme-prod \
        --billing-table acme-billing.export.gcp_billing_export_v1_000000_000000_000000

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--project` names
the project whose logs and secrets are read and in which the cost query runs. `--target` puts
every API and the token endpoint (`<target>/token`) at one address, the fake's under
`tests/fakes/cloud_service.py` to run without a network; `--logging-target`,
`--bigquery-target`, `--secrets-target`, `--monitoring-target`, `--aiplatform-target`,
`--iam-target` and `--token-endpoint` override one each. `--metrics` names a JSON file of
named metrics and their PromQL (ADR-0328); `--model-service` the model service's description
in the billing export.
Credentials are never arguments: the connector reads the value of a credential at the moment
of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call
references (`README.md`).
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
    parser.add_argument("--monitoring-target", default=None, help="the monitoring API's address")
    parser.add_argument("--aiplatform-target", default=None, help="the model API's address")
    parser.add_argument("--iam-target", default=None, help="the identity API's address")
    parser.add_argument(
        "--metrics", default=None, help="a JSON file of named metrics and their PromQL"
    )
    parser.add_argument(
        "--model-service", default="Vertex AI", help="the model service in the billing export"
    )
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
        monitoring=args.monitoring_target,
        aiplatform=args.aiplatform_target,
        iam=args.iam_target,
        metrics=serving.load_metrics(args.metrics),
        model_service=args.model_service,
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
