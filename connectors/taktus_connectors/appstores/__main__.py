"""Run the app stores connector as a process.

    uv run python -m taktus_connectors.appstores --port 9140

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`.
`--app-store-target` and `--play-target` are the two stores' API addresses, each its store's own
by default; `--target` sets both, as a fake that serves both does
(`tests/fakes/app_stores_service.py`). Credentials are never arguments: the connector reads the
value of a credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE`
names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.appstores.config import APP_STORE, PLAY, Config
from taktus_connectors.appstores.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The app stores connector.", 9140)
    parser.add_argument("--app-store-target", default=APP_STORE, help="the iOS store's API")
    parser.add_argument("--play-target", default=PLAY, help="the Android store's API")
    parser.add_argument("--target", default="", help="one address for both stores' APIs")
    args = parser.parse_args(argv)
    config = Config(
        args.target or args.app_store_target, args.target or args.play_target, args.timeout
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
