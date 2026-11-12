"""Run the cloud connector as a process.

    uv run python -m taktus_connectors.aws --port 9108 --services-region eu-central-1

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is
Cost Explorer's address (default the provider's own). `--logs-target` and `--secrets-target`
are CloudWatch Logs' and Secrets Manager's, by default the provider's in `--services-region`;
where `--target` is given and they are not, they follow it. Point `--target` at the fake under
`tests/fakes/cloud_billing_service.py` to run every API without a network. `--log-group` is the
log group a log query reads when the call names no `source`. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.aws.operations import REGION, TARGET, Config
from taktus_connectors.aws.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The cloud connector.", 9108)
    parser.add_argument("--target", default=TARGET, help="Cost Explorer's address")
    parser.add_argument("--region", default=REGION, help="the region Cost Explorer is signed for")
    parser.add_argument(
        "--services-region", default=REGION, help="the region logs and secrets are read in"
    )
    parser.add_argument("--logs-target", default=None, help="CloudWatch Logs' address")
    parser.add_argument("--secrets-target", default=None, help="Secrets Manager's address")
    parser.add_argument("--log-group", default=None, help="the log group read without `source`")
    args = parser.parse_args(argv)
    config = Config(
        args.target,
        args.region,
        args.timeout,
        services_region=args.services_region,
        logs_target=args.logs_target,
        secrets_target=args.secrets_target,
        log_group=args.log_group,
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
