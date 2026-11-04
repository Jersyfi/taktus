"""Run the calendar connector as a process.

    uv run python -m taktus_connectors.calendar --port 9121 \
        --target https://calendar.example [--caldav] [--zone Europe/Berlin]

It serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
calendar server's base address; a call names the calendar's path under it. `--caldav` reads it
as a CalDAV server, otherwise the path is an iCalendar file. `--zone` is the zone a time without
one is read in (default UTC). Credentials are never arguments: the connector reads the value of
a credential at the moment of a call, from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names,
under the name the call references (`README.md`).
"""

from __future__ import annotations

import sys
from zoneinfo import ZoneInfo

from taktus_connectors import serving
from taktus_connectors.calendar.operations import Config
from taktus_connectors.calendar.server import served


def main(argv: list[str] | None = None) -> int:
    parser = serving.arguments("The calendar connector.", 9121)
    parser.add_argument("--target", default="http://127.0.0.1:8080", help="the server's address")
    parser.add_argument("--caldav", action="store_true", help="the server answers CalDAV")
    parser.add_argument("--zone", default="UTC", help="the zone of a time without one")
    args = parser.parse_args(argv)
    ZoneInfo(args.zone)  # an unknown zone stops the start, not a call
    config = Config(args.target, caldav=args.caldav, zone=args.zone, timeout=args.timeout)
    return serving.serve(served(config, args.fault), args)


if __name__ == "__main__":
    sys.exit(main())
