"""Run the workload connector as a process.

    uv run python -m taktus_connectors.kubernetes --port 9130 \
        --target https://cluster.example:6443 --namespace shop

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API server's address; point it at the fake under `tests/fakes/workload_cluster.py` to run
without a cluster. `--namespace` is the one namespace whose deployments it serves, `default`
unless given. `--ca-file` names the cluster's certificate authority, where the API server's
certificate is not one the system trusts. Credentials are never arguments: the connector reads
the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.kubernetes.operations import Config
from taktus_connectors.kubernetes.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The workload connector.", 9130)
    parser.add_argument("--target", default="", help="the API server's address (required)")
    parser.add_argument("--namespace", default="default", help="the namespace served")
    parser.add_argument("--ca-file", default=None, help="the cluster's certificate authority")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required")
    config = Config(args.target, args.namespace, args.timeout, args.ca_file)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
