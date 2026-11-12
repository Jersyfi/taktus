"""Run the transactional mail connector as a process.

    uv run python -m taktus_connectors.resend --port 9181 --from support@example.org

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.resend.com` unless given; point it at the fake under
`tests/fakes/mail_api_service.py` to run without a network. `--from` is the address messages
and broadcasts are sent from, on a domain the account verified. Credentials are never
arguments: the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.resend.api import TARGET, Config
from taktus_connectors.resend.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The transactional mail connector.", 9181)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument(
        "--from",
        dest="sender",
        default="",
        help="the address messages are sent from, on a verified domain (required)",
    )
    args = parser.parse_args(argv)
    if not args.sender and not args.list_faults:
        parser.error("--from is required")
    config = Config(args.target, args.sender, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
