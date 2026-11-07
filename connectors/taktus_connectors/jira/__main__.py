"""Run the work tracker connector as a process.

    uv run python -m taktus_connectors.jira --target https://<site>.atlassian.net \
        --project KEY --port 9155

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
site's address; point it at the fake under `tests/fakes/task_rest_service.py` to run without a
network. `--project` is the key of the one project it reads: the API answers a search only
when the query is bounded. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.jira.operations import Config
from taktus_connectors.jira.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The work tracker connector.", 9155)
    parser.add_argument("--target", default="", help="the site's address (required)")
    parser.add_argument("--project", default="", help="the project's key (required)")
    args = parser.parse_args(argv)
    if not args.list_faults and not (args.target and args.project):
        parser.error("--target and --project are required")
    config = Config(args.target, args.project, args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
