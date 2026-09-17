"""Run the reference connector as a process.

    python -m taktus.adapters.driven.connectors.github --port 9100 --repository owner/name

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
base URL of the service's API; point it at the fake under `tests/fakes/repository_service.py`
to run without a network. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the environment or a file, under the name the call
references (`README.md`).
"""

from __future__ import annotations

import argparse
import sys

from taktus.adapters.driven.connectors.github.faults import FAULTS, check_of
from taktus.adapters.driven.connectors.github.server import Config, build_server, log

DEFAULT_TARGET = "https://api.github.com"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The reference repository connector.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--path", default="/mcp", help="where MCP is served")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="base URL of the service's API")
    parser.add_argument("--repository", help="owner/name of the repository")
    parser.add_argument("--fault", choices=sorted(FAULTS), help="violate exactly one check")
    parser.add_argument(
        "--list-faults", action="store_true", help="print every fault with the check it breaks"
    )
    args = parser.parse_args(argv)
    if args.list_faults:
        for fault, what in FAULTS.items():
            sys.stdout.write(f"{fault}\t{check_of(fault)}\t{what}\n")
        return 0
    if not args.repository:
        parser.error("--repository is required")
    config = Config(
        target=args.target,
        repository=args.repository,
        host=args.host,
        port=args.port,
        path=args.path,
        fault=args.fault,
    )
    if config.fault:
        log(f"FAULT {config.fault}: {FAULTS[config.fault]}")
    log(f"serving {config.repository} at http://{config.host}:{config.port}{config.path}")
    build_server(config).run(
        "streamable-http",
        host=config.host,
        port=config.port,
        streamable_http_path=config.path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
