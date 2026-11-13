"""Run the books connector as a process.

    uv run python -m taktus_connectors.erpnext --target https://books.example --port 9158 \
        --customer "Online customers" --income-account "Sales - EX" --tax-account "VAT - EX"

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
site's address; point it at the fake under `tests/fakes/books_service.py` to run without a
network. Credentials are never arguments: the connector reads the value of a credential at the
moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names.
"""

from __future__ import annotations

import sys

from taktus_connectors import serving
from taktus_connectors.erpnext.operations import Config
from taktus_connectors.erpnext.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The books connector.", 9158)
    parser.add_argument("--target", default="", help="the site's address")
    parser.add_argument("--customer", default="", help="the collective customer of the drafts")
    parser.add_argument("--income-account", default="", help="the account a line books to")
    parser.add_argument("--tax-account", default="", help="the account a draft's tax books to")
    parser.add_argument("--company", default="", help="the company, where the site has several")
    args = parser.parse_args(argv)
    if not args.list_faults:
        for name in ("target", "customer", "income_account", "tax_account"):
            if not getattr(args, name):
                parser.error(f"--{name.replace('_', '-')} is required")
    config = Config(
        args.target,
        args.customer,
        args.income_account,
        args.tax_account,
        company=args.company or None,
        timeout=args.timeout,
    )
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
