"""Run the website connector as a process.

    uv run python -m taktus_connectors.sanity --port 9183 --target https://abc123.api.sanity.io

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
project's API address; point it at the fake under `tests/fakes/content_lake_service.py` to run
without a network. Credentials are never arguments: the connector reads the value of a
credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, under
the name the call references (`README.md`).
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.sanity.operations import API_VERSION, Config, Fields
from taktus_connectors.sanity.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The website connector.", 9183)
    parser.add_argument("--target", default="", help="the project's API address (required)")
    parser.add_argument("--dataset", default="production", help="the dataset the posts live in")
    parser.add_argument("--api-version", default=API_VERSION, help="the dated API version")
    parser.add_argument("--type", default="post", help="the document type of a post")
    parser.add_argument("--studio", default="", help="the Studio's address, for a post's link")
    parser.add_argument("--title-field", default="title", help="the field of a post's title")
    parser.add_argument("--slug-field", default="slug", help="the field of a post's slug")
    parser.add_argument("--body-field", default="body", help="the field of a post's body")
    parser.add_argument("--excerpt-field", default="excerpt", help="the field of an excerpt")
    args = parser.parse_args(argv)
    if not args.target and not args.list_faults:
        parser.error("--target is required")
    config = Config(
        args.target,
        dataset=args.dataset,
        api_version=args.api_version,
        type=args.type,
        studio=args.studio,
        fields=Fields(args.title_field, args.slug_field, args.body_field, args.excerpt_field),
        timeout=args.timeout,
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
