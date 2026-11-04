"""Run the expiry connector as a process.

    uv run python -m taktus_connectors.expiry --port 9120 \
        --certificate www.example:443 --certificate api.example:443 \
        --target https://rdap.registry.example

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--certificate`
names one TLS endpoint a call may read, repeated for each; `--target` is the base address of
the RDAP server; `--ca-file` adds an authority the verification trusts. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.expiry.operations import Config, endpoint
from taktus_connectors.expiry.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The expiry connector.", 9120)
    parser.add_argument(
        "--certificate",
        action="append",
        default=[],
        metavar="HOST:PORT",
        help="a TLS endpoint whose certificate a call may read; repeat for each",
    )
    parser.add_argument("--target", default="", help="the RDAP server's base address")
    parser.add_argument("--ca-file", default=None, help="an authority the verification trusts")
    args = parser.parse_args(argv)
    config = Config(
        endpoints=frozenset(endpoint(e) for e in args.certificate),
        rdap=args.target,
        ca_file=args.ca_file,
        timeout=args.timeout,
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
