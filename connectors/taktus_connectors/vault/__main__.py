"""Run the secret store connector as a process.

    uv run python -m taktus_connectors.vault --port 9124 --target https://vault.example:8200

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
store's address and has no default; point it at the fake under
`tests/fakes/secret_store_service.py` to run without a network. `--mount` is the KV version 2
engine's mount (default `secret`), `--folder` the folder under it the walk starts in (default
its root), `--namespace` the namespace every request names. `--path` is not the folder: it is
where MCP is served, as for every connector here. Credentials are never arguments: the
connector reads the value of a credential at the moment of a call, from the file
`TAKTUS_CREDENTIAL_<NAME>_FILE` names, under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.vault.operations import MOUNT, Config
from taktus_connectors.vault.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The secret store connector.", 9124)
    parser.add_argument("--target", default="", help="the store's address (required)")
    parser.add_argument("--mount", default=MOUNT, help="the KV version 2 engine's mount")
    parser.add_argument("--folder", default="", help="the folder the walk starts in")
    parser.add_argument("--namespace", default=None, help="the namespace requests name")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required")
    config = Config(args.target, args.mount, args.folder, args.namespace or None, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
