"""Run the mail connector, or its relay, as a process.

    uv run python -m taktus_connectors.mail --port 9103 \
        --imap mail.example:993 --smtp mail.example:587 --user support@example.org
    uv run python -m taktus_connectors.mail relay \
        --imap mail.example:993 --smtp mail.example:587 --user support@example.org \
        --intake https://taktus.example/intake/channel.mail

The first serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. The second
reads the inbox every `--interval` seconds and delivers what is new to the intake. Point both
at the fake under `tests/fakes/mail_service.py` with `--security none` to run without a
network. Credentials are never arguments: both read them from the files
`TAKTUS_CREDENTIAL_<NAME>_FILE` names (`README.md`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from taktus_connectors import serving
from taktus_connectors.mail.protocol import SECURITY, Config
from taktus_connectors.mail.relay import relay
from taktus_connectors.mail.server import served


def _server(value: str, default_port: int) -> tuple[str, int]:
    host, _, port = value.rpartition(":") if ":" in value else (value, "", "")
    return (host or value), int(port) if port else default_port


def _mail_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--imap", default="127.0.0.1:993", help="host:port of the IMAP server")
    parser.add_argument("--smtp", default="127.0.0.1:587", help="host:port of the SMTP server")
    parser.add_argument("--user", default="taktus@localhost", help="the mailbox's login")
    parser.add_argument("--address", help="the address messages are sent from; --user if absent")
    parser.add_argument("--security", choices=SECURITY, default="tls")
    parser.add_argument("--inbox", default="INBOX")
    parser.add_argument("--sent", default="Sent")
    parser.add_argument(
        "--server-files-sent",
        action="store_true",
        help="the server files every message it accepted in the sent folder itself",
    )


def config_of(args: argparse.Namespace) -> Config:
    imap_host, imap_port = _server(args.imap, 993)
    smtp_host, smtp_port = _server(args.smtp, 587)
    return Config(
        imap_host=imap_host,
        imap_port=imap_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        user=args.user,
        address=args.address or args.user,
        security=args.security,
        inbox=args.inbox,
        sent=args.sent,
        file_sent=not args.server_files_sent,
        timeout=args.timeout,
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["relay"]:
        parser = argparse.ArgumentParser(description="The mail relay.")
        _mail_arguments(parser)
        parser.add_argument("--intake", required=True, help="the channel's intake address")
        parser.add_argument("--interval", type=float, default=60.0, help="seconds between passes")
        parser.add_argument("--once", action="store_true", help="one pass, then stop")
        parser.add_argument("--timeout", type=float, default=30.0)
        args = parser.parse_args(argv[1:])
        asyncio.run(relay(config_of(args), args.intake, interval=args.interval, once=args.once))
        return 0
    parser = serving.arguments("The mail connector.", 9103)
    _mail_arguments(parser)
    args = parser.parse_args(argv)
    return serving.serve(served(config_of(args), args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
