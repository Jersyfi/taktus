"""Run the metrics connector as a process.

    uv run python -m taktus_connectors.prometheus --port 9104 \
        --target http://metrics:9090

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
base address of the store; point it at the fake under `tests/fakes/metrics_service.py` to run
without a network. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.prometheus.operations import Config
from taktus_connectors.prometheus.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The metrics connector.", 9104)
    parser.add_argument("--target", default="http://127.0.0.1:9090", help="the store's address")
    args = parser.parse_args(argv)
    return serving.serve(served(Config(args.target, args.timeout), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
