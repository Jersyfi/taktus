"""Run the store reviews connector of the second store as a process.

    uv run python -m taktus_connectors.googleplay --port 9147

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address and `--token-url` the token endpoint (defaults the store's own); point both at
the fake under `tests/fakes/review_replies_service.py` to run without a network
(`--token-url /token` takes the path on `--target`). Credentials are never arguments: the
connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.googleplay.operations import TARGET, TOKEN_URL, Config
from taktus_connectors.googleplay.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The store reviews connector.", 9147)
    parser.add_argument("--target", default=TARGET, help="the API's address")
    parser.add_argument("--token-url", default=TOKEN_URL, help="the token endpoint")
    args = parser.parse_args(argv)
    config = Config(args.target, args.token_url, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
