"""Run the vendor connector as a process.

    uv run python -m taktus_connectors.vendor --port 9106 \
        --upstream https://mcp.vendor.example/mcp --manifest manifest.json

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--upstream` is
the MCP URL of the vendor's server, which the operator or the vendor runs. `--manifest` is the
manifest of its effects. Without it, `--capability` names the capability its reading tools are
served under, and `--credential` the requesting identity's credential (default
`VENDOR_TOKEN`). Credentials are never arguments: the connector reads the value at the moment
of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names (`README.md`).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from taktus_connectors import serving
from taktus_connectors.vendor.manifest import ManifestError
from taktus_connectors.vendor.server import NAME, faults, prepare, served
from taktus_connectors.vendor.upstream import Upstream
from taktus_connectors.vendor.wrapping import PlanError, Wrapper

EXIT_REFUSED = 2


def log(message: str) -> None:
    sys.stderr.write(f"{serving.now()} {NAME} {message}\n")
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The vendor connector.", 9106)
    parser.add_argument("--upstream", required=True, help="the MCP URL of the vendor's server")
    parser.add_argument("--manifest", type=Path, help="the manifest of the server's effects")
    parser.add_argument("--capability", help="without a manifest: the capability served")
    parser.add_argument("--credential", help="without a manifest: the actions credential")
    args = parser.parse_args(argv)
    upstream = Upstream(args.upstream, timeout=args.timeout)
    try:
        plan = asyncio.run(
            prepare(
                upstream,
                manifest=args.manifest,
                capability=args.capability,
                credential=args.credential,
                log=log,
            )
        )
    except (PlanError, ManifestError) as error:
        log(f"refused to start: {error}")
        return EXIT_REFUSED
    if args.list_faults:
        for fault, what in faults(plan).items():
            sys.stdout.write(f"{fault}\t{fault[:4]}\t{what}\n")
        return 0
    for withheld in plan.withheld:
        log(f"withheld {withheld.tool}: {withheld.reason}")
    if plan.manifest is None:
        log("no manifest: read only, and experimental (ADR-0117)")
    return serving.serve(served(Wrapper(upstream, plan), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
