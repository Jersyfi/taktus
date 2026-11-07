"""Run the warehouse connector as a process.

    uv run python -m taktus_connectors.bigquery --port 9138 \
        --project shop-analytics --dataset product_copy

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://bigquery.googleapis.com` unless given; point it at the fake under
`tests/fakes/warehouse_service.py` to run without the service. `--project` is the project the
queries run in, `--dataset` the dataset unqualified table names resolve to: the copy without
personal fields. `--location` names where the jobs run, where the dataset is not in the US or
EU multi-region. Credentials are never arguments: the connector reads the value of a credential
at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the
call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.bigquery.operations import TARGET, Config
from taktus_connectors.bigquery.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The warehouse connector.", 9138)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--project", default="", help="the project the queries run in (required)")
    parser.add_argument("--dataset", default="", help="the dataset of the copy (required)")
    parser.add_argument("--location", default=None, help="where the jobs run")
    args = parser.parse_args(argv)
    if not (args.project and args.dataset) and not args.list_faults:
        parser.error("--project and --dataset are required")
    config = Config(args.target, args.project, args.dataset, args.location, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
