#!/usr/bin/env python3
"""The MCP project's reference time server, served over streamable HTTP for the gates.

`mcp-server-time` is a vendor's MCP server in the sense of ADR-0117: third-party code, written
for MCP and for nothing of Taktus, installed from the lock file as a test dependency. It speaks
stdio when started as its vendor ships it. The vendor connector reaches a server at an MCP URL,
so this runner serves the very same server object over streamable HTTP. Nothing of the server
is changed: its tools, their hints and their errors are the vendor's. It reaches no network.

Runnable as `python tests/fakes/vendor_time_server.py --port 9208`.
"""

from __future__ import annotations

import argparse

from mcp_server_time.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9208)
    parser.add_argument("--local-timezone", default="UTC")
    args = parser.parse_args()
    create_server(args.local_timezone).run(
        "streamable-http", host=args.host, port=args.port, streamable_http_path="/mcp"
    )


if __name__ == "__main__":
    main()
