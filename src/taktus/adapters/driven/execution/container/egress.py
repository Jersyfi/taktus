#!/usr/bin/env python3
"""The egress gateway of an instance: one for every job, admitting each the hosts its token
names (ADR-0115).

Runs as one container of the instance next to every job's unit, or as a Deployment in the
cluster's execution namespace. Standard library only, because it runs from a plain Python image
as well as from Taktus's own. It does two things:

- **proxy**: an HTTP proxy on `--listen` that admits a request only with a token in
  `Proxy-Authorization` (basic, user `taktus`), and only to the hosts that token names — by
  `CONNECT host:port` for TLS and by absolute-URI requests for plain HTTP. Every other host is
  answered 403, and a request without a valid token 407. The token is minted per job by the
  execution adapter and signed with the instance's gateway key (`--key-file`): a unit cannot
  name a host its token does not, and cannot use another job's token once that job's deadline
  has passed. The unit's network has no other route out;
- **inbound**, the container adapter's only: on `--inbound`, a request to
  `/units/<unit>/<port>/<path>` is forwarded to that unit's worker contract as `/<path>`. It
  listens only on the address the gateway had when it started, on the network the control plane
  reaches, and so never on a job's network: a unit cannot reach another unit's contract through
  it.

An entry of a token's hosts is `host` or `host:port`; without a port every port of that host is
admitted, with one only that port. No wildcard, no pattern (contracts/worker/v1 §3). A token
that names no host admits nothing. With `--refuse-job-networks` the proxy also refuses an
address on any network the gateway joined after it started — the jobs' own networks — whatever
a token names, so that no token reaches another job's unit.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import socket
import sys
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

type Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Coroutine[Any, Any, None]]
type Address = ipaddress.IPv4Address | ipaddress.IPv6Address

PROXY_USER = "taktus"
UNIT_NAME = re.compile(r"^taktus-unit-[a-z0-9-]+$")
KEY_WAIT_SECONDS = 60.0


def log(message: str) -> None:
    sys.stderr.write(f"egress {message}\n")
    sys.stderr.flush()


class Allowlist:
    def __init__(self, entries: list[str]) -> None:
        self.entries = tuple(entries)
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


# --- the token: what one job may reach -----------------------------------------------------------


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(key: bytes, *, job: str, hosts: list[str] | tuple[str, ...], expires: int) -> str:
    """A job's token: the hosts it may reach and when it stops admitting anything, signed with
    the gateway's key. URL-safe, so that it stands in a proxy URL as the password."""
    payload = json.dumps(
        {"v": 1, "job": job, "hosts": list(hosts), "exp": expires},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    body = _encode(payload)
    signature = hmac.new(key, body.encode(), hashlib.sha256).digest()
    return f"{body}.{_encode(signature)}"


def verify(key: bytes, token: str, *, now: float) -> Allowlist | None:
    """The hosts a token admits, or None when it is not one the key signed or its job's time is
    over."""
    body, separator, signature = token.partition(".")
    if not separator:
        return None
    expected = hmac.new(key, body.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_decode(signature), expected):
            return None
        payload = json.loads(_decode(body))
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("v") != 1:
        return None
    expires = payload.get("exp")
    hosts = payload.get("hosts")
    if not isinstance(expires, int) or expires <= now or not isinstance(hosts, list):
        return None
    return Allowlist([str(h) for h in hosts])


def presented(headers: list[bytes]) -> str | None:
    """The password of a basic `Proxy-Authorization` for the user `taktus`, if one is there."""
    for header in headers:
        name, _, value = header.partition(b":")
        if name.strip().lower() != b"proxy-authorization":
            continue
        scheme, _, credentials = value.strip().partition(b" ")
        if scheme.lower() != b"basic":
            return None
        try:
            user, _, password = base64.b64decode(credentials.strip()).decode().partition(":")
        except ValueError:
            return None
        return password if user == PROXY_USER else None
    return None


def signed(key: Callable[[], bytes]) -> Callable[[list[bytes]], Allowlist | None]:
    """The allowlist of whichever job's token a request presents; None without a valid one."""

    def allowlist_of(headers: list[bytes]) -> Allowlist | None:
        token = presented(headers)
        return None if token is None else verify(key(), token, now=time.time())

    return allowlist_of


# --- the jobs' networks: never a target -------------------------------------------------------


def _routes() -> list[tuple[str, ipaddress.IPv4Network]]:
    """The directly attached IPv4 networks by interface, from the kernel's routing table; none
    where there is no such table."""
    try:
        lines = Path("/proc/net/route").read_text(encoding="ascii").splitlines()[1:]
    except OSError:
        return []
    found: list[tuple[str, ipaddress.IPv4Network]] = []
    for line in lines:
        fields = line.split()
        if len(fields) < 8 or fields[2] != "00000000":  # a gateway: not attached
            continue
        destination = socket.inet_ntoa(int(fields[1], 16).to_bytes(4, "little"))
        mask = socket.inet_ntoa(int(fields[7], 16).to_bytes(4, "little"))
        try:
            found.append((fields[0], ipaddress.IPv4Network(f"{destination}/{mask}")))
        except ValueError:
            continue
    return found


def job_networks(boot: Address | None) -> list[ipaddress.IPv4Network]:
    """Every attached network but the one the gateway started on: the jobs' networks."""
    routes = _routes()
    home = {name for name, network in routes if boot is not None and boot in network}
    return [network for name, network in routes if name not in home and network.prefixlen > 0]


def boot_address() -> Address | None:
    """The address the gateway has on the network it started on."""
    try:
        return ipaddress.ip_address(socket.gethostbyname(socket.gethostname()))
    except (OSError, ValueError):
        return None


# --- streams --------------------------------------------------------------------------------------


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


async def read_head(reader: asyncio.StreamReader) -> tuple[bytes, list[bytes]] | None:
    try:
        request_line = await asyncio.wait_for(reader.readline(), 30)
        headers: list[bytes] = []
        while (line := await asyncio.wait_for(reader.readline(), 30)) not in (
            b"\r\n",
            b"\n",
            b"",
        ):
            headers.append(line)
    except (TimeoutError, OSError, ValueError):
        return None
    return request_line, headers


async def refuse(writer: asyncio.StreamWriter, status: str, why: str, extra: str = "") -> None:
    body = (why + "\n").encode()
    writer.write(
        f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
        f"{extra}Connection: close\r\n\r\n".encode()
        + body
    )
    try:
        await writer.drain()
    except OSError:
        pass
    writer.close()


# --- proxy: the way out ---------------------------------------------------------------------


async def resolve(host: str, port: int) -> list[Address]:
    loop = asyncio.get_running_loop()
    found = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [ipaddress.ip_address(info[4][0]) for info in found]


def proxy(
    allowlist_of: Callable[[list[bytes]], Allowlist | None],
    forbidden: Callable[[Address], bool] = lambda address: False,
) -> Handler:
    """The proxy: `allowlist_of` is the job's allowlist for a request's headers, None when the
    request carries no valid token; `forbidden` names addresses no token reaches."""

    async def connect(host: str, port: int) -> tuple[Any, Any] | str:
        try:
            addresses = await resolve(host, port)
        except OSError as error:
            return f"{host}:{port}: {error}"
        allowed = [a for a in addresses if not forbidden(a)]
        if not allowed:
            return f"{host}:{port} is on a job's network"
        try:
            return await asyncio.open_connection(str(allowed[0]), port)
        except OSError as error:
            return f"{host}:{port}: {error}"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await read_head(reader)
        if head is None:
            writer.close()
            return
        request_line, headers = head
        parts = request_line.decode(errors="replace").split()
        if len(parts) != 3:
            await refuse(writer, "400 Bad Request", "not an HTTP request")
            return
        method, target, version = parts
        allowlist = allowlist_of(headers)
        if allowlist is None:
            log(f"refused {method} {target}: no valid proxy authorisation")
            # A 407 names the scheme it accepts (RFC 9110 §11.7.1). A client that negotiates,
            # as git does by default, sends no credentials until it reads one (issue #356).
            await refuse(
                writer,
                "407 Proxy Authentication Required",
                "this proxy admits a job's token only",
                f'Proxy-Authenticate: Basic realm="{PROXY_USER}"\r\n',
            )
            return
        if method.upper() == "CONNECT":
            host, _, port_text = target.rpartition(":")
            port = int(port_text) if port_text.isdigit() else 443
            if not allowlist.admits(host, port):
                log(f"refused CONNECT {host}:{port}")
                await refuse(writer, "403 Forbidden", f"host {host}:{port} is not in the allowlist")
                return
            upstream = await connect(host, port)
            if isinstance(upstream, str):
                await refuse(writer, "502 Bad Gateway", upstream)
                return
            writer.write(f"{version} 200 Connection established\r\n\r\n".encode())
            await writer.drain()
            log(f"admitted CONNECT {host}:{port}")
            await splice(reader, writer, *upstream)
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
        upstream = await connect(host, port)
        if isinstance(upstream, str):
            await refuse(writer, "502 Bad Gateway", upstream)
            return
        up_reader, up_writer = upstream
        path = url.path or "/"
        if url.query:
            path += "?" + url.query
        kept = [h for h in headers if not h.lower().startswith(b"proxy-")]
        up_writer.write(f"{method} {path} {version}\r\n".encode() + b"".join(kept) + b"\r\n")
        await up_writer.drain()
        log(f"admitted {method} {host}:{port}")
        await splice(reader, writer, up_reader, up_writer)

    return handle


# --- inbound: the way in --------------------------------------------------------------------


def inbound() -> Handler:
    """`/units/<unit>/<port>/<path>` to that unit's `/<path>`, one request per connection: the
    request is forwarded with `Connection: close`, so that a client that keeps a connection
    open asks the next request on a new one, routed again."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await read_head(reader)
        if head is None:
            writer.close()
            return
        request_line, headers = head
        parts = request_line.decode(errors="replace").split()
        if len(parts) != 3:
            await refuse(writer, "400 Bad Request", "not an HTTP request")
            return
        method, target, version = parts
        segments = target.split("/", 4)
        if (
            len(segments) < 4
            or segments[1] != "units"
            or not UNIT_NAME.match(segments[2])
            or not segments[3].isdigit()
        ):
            await refuse(writer, "404 Not Found", "a request names /units/<unit>/<port>/<path>")
            return
        unit, port = segments[2], int(segments[3])
        rest = "/" + (segments[4] if len(segments) > 4 else "")
        try:
            up_reader, up_writer = await asyncio.open_connection(unit, port)
        except OSError as error:
            await refuse(writer, "502 Bad Gateway", f"{unit}:{port}: {error}")
            return
        kept = [h for h in headers if h.split(b":", 1)[0].strip().lower() != b"connection"]
        up_writer.write(
            f"{method} {rest} {version}\r\n".encode()
            + b"".join(kept)
            + b"Connection: close\r\n\r\n"
        )
        await up_writer.drain()
        # The request's body goes on while the answer's head is read and marked to close too:
        # a unit's server need not say so itself.
        body = asyncio.create_task(pipe(reader, up_writer))
        answer = await read_head(up_reader)
        if answer is None:
            body.cancel()
            await refuse(writer, "502 Bad Gateway", f"{unit}:{port} gave no answer")
            return
        status, answer_headers = answer
        kept = [h for h in answer_headers if h.split(b":", 1)[0].strip().lower() != b"connection"]
        writer.write(status + b"".join(kept) + b"Connection: close\r\n\r\n")
        await writer.drain()
        await asyncio.gather(body, pipe(up_reader, writer))

    return handle


# --- the process ----------------------------------------------------------------------------------


async def wait_for_key(path: Path, within: float = KEY_WAIT_SECONDS) -> None:
    """The key arrives after the start, into memory (the container adapter); a mounted one is
    there at once (the cluster)."""

    def present() -> bool:
        return path.is_file() and bool(path.read_bytes().strip())

    loop = asyncio.get_running_loop()
    deadline = loop.time() + within
    while not present():
        if loop.time() >= deadline:
            raise SystemExit(f"egress: no key at {path} within {within:g}s")
        await asyncio.sleep(0.1)


async def serve(args: argparse.Namespace) -> None:
    key_file = Path(args.key_file)
    await wait_for_key(key_file)

    def key() -> bytes:
        # Read for every request, so that a rotated key needs no restart.
        return key_file.read_bytes().strip()

    boot = boot_address()
    if args.refuse_job_networks:

        def forbidden(address: Address) -> bool:
            if address.is_loopback or address == boot:
                return True
            return any(address in network for network in job_networks(boot))

    else:

        def forbidden(address: Address) -> bool:
            return False

    servers = [
        await asyncio.start_server(
            proxy(signed(key), forbidden),
            "0.0.0.0",  # noqa: S104 — every network of the gateway: the jobs reach it there
            args.listen,
        ),
    ]
    if args.inbound is not None:
        if boot is None:
            raise SystemExit("egress: the gateway's own address is not known, so no inbound")
        servers.append(await asyncio.start_server(inbound(), str(boot), args.inbound))
        log(f"inbound on {boot}:{args.inbound}")
    log(f"proxy on {args.listen}, admitting the hosts of each job's token")
    await asyncio.gather(*(s.serve_forever() for s in servers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--listen", type=int, default=3128, help="the proxy port")
    parser.add_argument("--key-file", required=True, help="the file that holds the gateway key")
    parser.add_argument("--inbound", type=int, help="the port the control plane reaches units on")
    parser.add_argument(
        "--refuse-job-networks",
        action="store_true",
        help="refuse every address on a network the gateway joined after it started",
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
