#!/usr/bin/env python3
"""The egress container of one job: the only way in and the only way out.

Runs inside a small container next to the job's unit, on the job's own internal network and
on the network the control plane reaches. It does two things, both with the standard library
only, because it runs from a plain Python image:

- **forward**: accepts connections on `--forward` and pipes them to the unit (`--to`), so that
  the control plane reaches the unit's worker contract through this container and nothing
  else on the job's network is reachable from outside;
- **proxy**: an HTTP proxy on `--listen` that admits exactly the hosts in `--allow` — by
  `CONNECT host:port` for TLS and by absolute-URI requests for plain HTTP — and answers 403
  to every other host. The unit's network has no route to the outside; this proxy is its only
  outbound path, and the allowlist is `frame.allowed_hosts` (W-13), made real here.

An entry in `--allow` is `host` or `host:port`; without a port every port of that host is
admitted, with one only that port. No wildcard, no pattern (contracts/worker/v1 §3). An empty
list means the proxy admits nothing, which is the default for every job.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any
from urllib.parse import urlsplit

type Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Coroutine[Any, Any, None]]


def log(message: str) -> None:
    sys.stderr.write(f"egress {message}\n")
    sys.stderr.flush()


class Allowlist:
    def __init__(self, entries: list[str]) -> None:
        self._any_port: set[str] = set()
        self._exact: set[tuple[str, int]] = set()
        for entry in entries:
            host, separator, port = entry.rpartition(":")
            if separator and port.isdigit():
                self._exact.add((host.lower(), int(port)))
            else:
                self._any_port.add(entry.lower())

    def admits(self, host: str, port: int) -> bool:
        host = host.lower()
        return host in self._any_port or (host, port) in self._exact


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def splice(
    a_reader: asyncio.StreamReader,
    a_writer: asyncio.StreamWriter,
    b_reader: asyncio.StreamReader,
    b_writer: asyncio.StreamWriter,
) -> None:
    await asyncio.gather(pipe(a_reader, b_writer), pipe(b_reader, a_writer))


# --- forward: the way in -------------------------------------------------------------------------


def forwarder(target_host: str, target_port: int) -> Handler:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_reader, up_writer = await asyncio.open_connection(target_host, target_port)
        except OSError as error:
            log(f"forward: the unit at {target_host}:{target_port} is not reachable: {error}")
            writer.close()
            return
        await splice(reader, writer, up_reader, up_writer)

    return handle


# --- proxy: the way out ---------------------------------------------------------------------


def proxy(allowlist: Allowlist) -> Handler:
    async def refuse(writer: asyncio.StreamWriter, status: str, why: str) -> None:
        body = (why + "\n").encode()
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), 30)
            headers: list[bytes] = []
            while (line := await asyncio.wait_for(reader.readline(), 30)) not in (
                b"\r\n",
                b"\n",
                b"",
            ):
                headers.append(line)
        except (TimeoutError, OSError):
            writer.close()
            return
        parts = request_line.decode(errors="replace").split()
        if len(parts) != 3:
            await refuse(writer, "400 Bad Request", "not an HTTP request")
            return
        method, target, version = parts
        if method.upper() == "CONNECT":
            host, _, port_text = target.rpartition(":")
            port = int(port_text) if port_text.isdigit() else 443
            if not allowlist.admits(host, port):
                log(f"refused CONNECT {host}:{port}")
                await refuse(writer, "403 Forbidden", f"host {host}:{port} is not in the allowlist")
                return
            try:
                up_reader, up_writer = await asyncio.open_connection(host, port)
            except OSError as error:
                await refuse(writer, "502 Bad Gateway", f"{host}:{port}: {error}")
                return
            writer.write(f"{version} 200 Connection established\r\n\r\n".encode())
            await writer.drain()
            log(f"admitted CONNECT {host}:{port}")
            await splice(reader, writer, up_reader, up_writer)
            return
        url = urlsplit(target)
        if url.scheme != "http" or not url.hostname:
            await refuse(writer, "400 Bad Request", "a proxy request names an absolute http URL")
            return
        host, port = url.hostname, url.port or 80
        if not allowlist.admits(host, port):
            log(f"refused {method} {host}:{port}")
            await refuse(writer, "403 Forbidden", f"host {host}:{port} is not in the allowlist")
            return
        try:
            up_reader, up_writer = await asyncio.open_connection(host, port)
        except OSError as error:
            await refuse(writer, "502 Bad Gateway", f"{host}:{port}: {error}")
            return
        path = url.path or "/"
        if url.query:
            path += "?" + url.query
        kept = [h for h in headers if not h.lower().startswith(b"proxy-")]
        up_writer.write(f"{method} {path} {version}\r\n".encode() + b"".join(kept) + b"\r\n")
        await up_writer.drain()
        log(f"admitted {method} {host}:{port}")
        await splice(reader, writer, up_reader, up_writer)

    return handle


async def serve(args: argparse.Namespace) -> None:
    allowlist = Allowlist([h for h in args.allow.split(",") if h])
    target_host, _, target_port = args.to.rpartition(":")
    servers = [
        await asyncio.start_server(proxy(allowlist), "0.0.0.0", args.listen),  # noqa: S104
        await asyncio.start_server(
            forwarder(target_host, int(target_port)),
            "0.0.0.0",  # noqa: S104 — the container's own interfaces
            args.forward,
        ),
    ]
    log(f"proxy on {args.listen} admitting [{args.allow}]; forwarding {args.forward} to {args.to}")
    async with servers[0], servers[1]:
        await asyncio.gather(*(s.serve_forever() for s in servers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--listen", type=int, default=3128, help="the proxy port")
    parser.add_argument("--forward", type=int, required=True, help="the port forwarded to the unit")
    parser.add_argument("--to", required=True, help="host:port of the unit")
    parser.add_argument("--allow", default="", help="comma-separated hosts the proxy admits")
    args = parser.parse_args(argv)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
