"""Run the newsletter connector as a process.

    uv run python -m taktus_connectors.mailchimp --port 9135 --target https://us6.api.mailchimp.com

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
address of the account's API, the data centre the account lives in; point it at the fake under
`tests/fakes/newsletter_service.py` to run without a network. Credentials are never arguments:
the connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.mailchimp.operations import Config
from taktus_connectors.mailchimp.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The newsletter connector.", 9135)
    parser.add_argument("--target", default="", help="the account's API address (required)")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required")
    config = Config(args.target, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
