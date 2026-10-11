"""Run the wiki connector as a process.

    uv run python -m taktus.adapters.driven.connectors.bookstack --target <base address>

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
wiki's base address, without `/api`; point it at the fake under `tests/fakes/wiki_service.py` to
run without a network. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import argparse
import sys

from taktus.adapters.driven.connectors.bookstack.faults import FAULTS, check_of
from taktus.adapters.driven.connectors.bookstack.server import Config, build_server, log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The wiki connector.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9102)
    parser.add_argument("--path", default="/mcp", help="where MCP is served")
    parser.add_argument("--target", help="the wiki's base address, without /api")
    parser.add_argument("--fault", choices=sorted(FAULTS), help="violate exactly one check")
    parser.add_argument(
        "--list-faults", action="store_true", help="print every fault with the check it breaks"
    )
    args = parser.parse_args(argv)
    if args.list_faults:
        for fault, what in FAULTS.items():
            sys.stdout.write(f"{fault}\t{check_of(fault)}\t{what}\n")
        return 0
    if not args.target:
        parser.error("--target is the wiki's base address; the connector knows no default")
    config = Config(
        target=args.target, host=args.host, port=args.port, path=args.path, fault=args.fault
    )
    if config.fault:
        log(f"FAULT {config.fault}: {FAULTS[config.fault]}")
    log(f"serving at http://{config.host}:{config.port}{config.path}")
    build_server(config).run(
        "streamable-http",
        host=config.host,
        port=config.port,
        streamable_http_path=config.path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
