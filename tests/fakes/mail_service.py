#!/usr/bin/env python3
"""A fake mail server: IMAP and SMTP on two ports, and a small HTTP interface for the tests.

The mail connector under `connectors/taktus_connectors/mail/` speaks IMAP and SMTP
through the standard library's clients. This fake answers the part of both protocols those
clients use, in plain text without TLS, and keeps every mailbox in memory. It exists so that the
connector can be exercised in CI without a network, an account or a secret: the conformance
gate starts it as a process, the adapter tests start it in threads.

What it enforces, because the connector's checks depend on it:

- **Authentication.** IMAP `LOGIN` and SMTP `AUTH PLAIN` need a login and a password the fake
  was started with (`FAKE_MAIL_ACCOUNTS`, `login:password,...`). SMTP refuses `MAIL` before a
  login. A wrong password is `NO` in IMAP and `535` in SMTP.
- **Mailboxes.** `INBOX` and `Sent`. `INBOX` holds one seeded message, `<seed-1@mail.example>`
  from `customer@mail.example`. A message submitted over SMTP to a login's own address is
  delivered into `INBOX`; every other one is only counted. A recipient at `refused.example` is
  refused with `550`.
- **IMAP**: `CAPABILITY`, `NOOP`, `LOGIN`, `LOGOUT`, `SELECT`, `EXAMINE`, `APPEND` with a
  literal, and `UID SEARCH` (`ALL`, `HEADER`, `KEYWORD`, `UNKEYWORD`, combined by AND), `UID
  FETCH` of `BODY.PEEK[]` and `UID STORE` of `+FLAGS`. A search by header matches its value as
  a substring, case-insensitively, as RFC 3501 says.

Test-only endpoints under `/_fake/` on the HTTP port: `GET /_fake/state` counts the messages of
every mailbox, the messages submitted and the logins; `GET /_fake/messages?mailbox=INBOX` lists
each message's UID, message identifier and flags; `POST /_fake/deliver` with a raw message puts
it into `INBOX` as if it had arrived; `POST /_fake/reset` empties everything back to the seed.
Standard library only; runnable as `python3 tests/fakes/mail_service.py`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socketserver
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

ACCOUNTS_VARIABLE = "FAKE_MAIL_ACCOUNTS"
SEED = (
    b"From: A customer <customer@mail.example>\r\n"
    b"To: taktus@mail.example\r\n"
    b"Subject: The export stopped\r\n"
    b"Date: Fri, 16 Oct 2026 08:15:00 +0000\r\n"
    b"Message-ID: <seed-1@mail.example>\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Since this morning the export answers with an error.\r\n"
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class Stored:
    uid: int
    raw: bytes
    flags: set[str] = field(default_factory=set)


@dataclass
class Store:
    accounts: dict[str, str]
    mailboxes: dict[str, list[Stored]] = field(default_factory=dict)
    next_uid: dict[str, int] = field(default_factory=dict)
    submitted: list[tuple[str, list[str], bytes]] = field(default_factory=list)
    logins: int = 0
    refused_logins: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.mailboxes = {"INBOX": [], "Sent": []}
            self.next_uid = {"INBOX": 1, "Sent": 1}
            self.submitted = []
            self.logins = 0
            self.refused_logins = 0
        self.put("INBOX", SEED)

    def name(self, mailbox: str) -> str | None:
        for known in self.mailboxes:
            if known.lower() == mailbox.lower():
                return known
        return None

    def put(self, mailbox: str, raw: bytes, flags: set[str] | None = None) -> int:
        with self.lock:
            uid = self.next_uid[mailbox]
            self.next_uid[mailbox] = uid + 1
            self.mailboxes[mailbox].append(Stored(uid, raw, set(flags or ())))
            return uid

    def admits(self, login: str, password: str) -> bool:
        with self.lock:
            ok = self.accounts.get(login) == password
            if ok:
                self.logins += 1
            else:
                self.refused_logins += 1
            return ok

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "mailboxes": {name: len(items) for name, items in self.mailboxes.items()},
                "submitted": len(self.submitted),
                "logins": self.logins,
                "refused_logins": self.refused_logins,
            }


# --- IMAP ----------------------------------------------------------------------------------------

TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|\(([^)]*)\)|\{(\d+)\}$|(\S+)')


def tokens(line: str) -> list[str]:
    out: list[str] = []
    for match in TOKEN.finditer(line):
        quoted, listed, literal, atom = match.groups()
        if quoted is not None:
            out.append(re.sub(r"\\(.)", r"\1", quoted))
        elif listed is not None:
            out.append(f"({listed})")
        elif literal is not None:
            out.append("{" + literal + "}")
        else:
            out.append(atom)
    return out


def header_values(raw: bytes, name: str) -> list[str]:
    message = message_from_bytes(raw)
    return [str(v) for v in message.get_all(name, [])]


class ImapHandler(socketserver.StreamRequestHandler):
    store: Store

    def send(self, line: str | bytes) -> None:
        data = line if isinstance(line, bytes) else line.encode()
        self.wfile.write(data + (b"" if data.endswith(b"\r\n") else b"\r\n"))

    def handle(self) -> None:
        self.user: str | None = None
        self.mailbox: str | None = None
        self.send("* OK fake IMAP ready")
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            literal = re.search(r"\{(\d+)\}$", line)
            data = b""
            if literal:
                self.send("+ go ahead")
                data = self.rfile.read(int(literal.group(1)))
                self.rfile.readline()
            parts = line.split(" ", 2)
            if len(parts) < 2:
                self.send("* BAD no command")
                continue
            tag, command = parts[0], parts[1].upper()
            rest = parts[2] if len(parts) > 2 else ""
            if not self.dispatch(tag, command, rest, data):
                return

    def dispatch(self, tag: str, command: str, rest: str, data: bytes) -> bool:
        store = self.store
        if command == "CAPABILITY":
            self.send("* CAPABILITY IMAP4rev1 AUTH=PLAIN")
        elif command == "NOOP":
            pass
        elif command == "LOGOUT":
            self.send("* BYE fake IMAP closing")
            self.send(f"{tag} OK LOGOUT completed")
            return False
        elif command == "LOGIN":
            args = tokens(rest)
            if len(args) != 2 or not store.admits(args[0], args[1]):
                self.send(f"{tag} NO [AUTHENTICATIONFAILED] invalid credentials")
                return True
            self.user = args[0]
        elif self.user is None:
            self.send(f"{tag} BAD log in first")
            return True
        elif command in ("SELECT", "EXAMINE"):
            name = store.name(tokens(rest)[0] if rest else "")
            if name is None:
                self.send(f"{tag} NO no such mailbox")
                return True
            self.mailbox = name
            with store.lock:
                count = len(store.mailboxes[name])
                uidnext = store.next_uid[name]
            self.send(f"* {count} EXISTS")
            self.send("* 0 RECENT")
            self.send("* FLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft)")
            self.send("* OK [UIDVALIDITY 1] valid")
            self.send(f"* OK [UIDNEXT {uidnext}] next")
            mode = "READ-ONLY" if command == "EXAMINE" else "READ-WRITE"
            self.send(f"{tag} OK [{mode}] {command} completed")
            return True
        elif command == "APPEND":
            args = tokens(rest)
            name = store.name(args[0]) if args else None
            if name is None:
                self.send(f"{tag} NO [TRYCREATE] no such mailbox")
                return True
            flags = set()
            if len(args) > 1 and args[1].startswith("("):
                flags = set(args[1].strip("()").split())
            uid = store.put(name, data, flags)
            self.send(f"{tag} OK [APPENDUID 1 {uid}] APPEND completed")
            return True
        elif command == "UID":
            return self.uid(tag, rest)
        else:
            self.send(f"{tag} BAD unknown command {command}")
            return True
        self.send(f"{tag} OK {command} completed")
        return True

    def uid(self, tag: str, rest: str) -> bool:
        store = self.store
        if self.mailbox is None:
            self.send(f"{tag} BAD select a mailbox first")
            return True
        sub, _, args_text = rest.partition(" ")
        sub = sub.upper()
        args = tokens(args_text)
        with store.lock:
            items = list(store.mailboxes[self.mailbox])
        if sub == "SEARCH":
            found = [m.uid for m in items if self.matches(m, args)]
            self.send("* SEARCH" + "".join(f" {u}" for u in found))
        elif sub == "FETCH":
            wanted = {int(u) for u in args[0].split(",") if u.isdigit()}
            for seq, m in enumerate(items, 1):
                if m.uid in wanted:
                    head = f"* {seq} FETCH (UID {m.uid} BODY[] {{{len(m.raw)}}}\r\n".encode()
                    self.wfile.write(head + m.raw + b")\r\n")
        elif sub == "STORE":
            wanted = {int(u) for u in args[0].split(",") if u.isdigit()}
            added = set(args[2].strip("()").split()) if len(args) > 2 else set()
            for seq, m in enumerate(items, 1):
                if m.uid in wanted:
                    with store.lock:
                        m.flags |= added
                    self.send(f"* {seq} FETCH (UID {m.uid} FLAGS ({' '.join(sorted(m.flags))}))")
        else:
            self.send(f"{tag} BAD unknown UID command {sub}")
            return True
        self.send(f"{tag} OK UID {sub} completed")
        return True

    @staticmethod
    def matches(message: Stored, criteria: list[str]) -> bool:
        i = 0
        while i < len(criteria):
            key = criteria[i].upper()
            if key == "ALL":
                i += 1
            elif key == "HEADER" and i + 2 < len(criteria) + 1:
                name, value = criteria[i + 1], criteria[i + 2].lower()
                if not any(value in v.lower() for v in header_values(message.raw, name)):
                    return False
                i += 3
            elif key == "KEYWORD":
                if criteria[i + 1] not in message.flags:
                    return False
                i += 2
            elif key == "UNKEYWORD":
                if criteria[i + 1] in message.flags:
                    return False
                i += 2
            else:
                return False
        return True


# --- SMTP ----------------------------------------------------------------------------------------


class SmtpHandler(socketserver.StreamRequestHandler):
    store: Store

    def send(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        user: str | None = None
        sender: str | None = None
        recipients: list[str] = []
        self.send("220 fake SMTP ready")
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            verb = line.split(" ", 1)[0].upper()
            arg = line[len(verb) :].strip()
            if verb in ("EHLO", "HELO"):
                if verb == "EHLO":
                    self.send("250-fake.mail.example")
                    self.send("250 AUTH PLAIN")
                else:
                    self.send("250 fake.mail.example")
            elif verb == "AUTH":
                mechanism, _, initial = arg.partition(" ")
                if mechanism.upper() != "PLAIN":
                    self.send("504 5.5.4 only PLAIN")
                    continue
                if not initial:
                    self.send("334 ")
                    initial = self.rfile.readline().decode().strip()
                try:
                    _, login, password = base64.b64decode(initial).decode().split("\0")
                except ValueError:
                    self.send("501 5.5.2 cannot decode")
                    continue
                if self.store.admits(login, password):
                    user = login
                    self.send("235 2.7.0 Authentication successful")
                else:
                    self.send("535 5.7.8 Authentication credentials invalid")
            elif verb == "MAIL":
                if user is None:
                    self.send("530 5.7.0 Authentication required")
                    continue
                sender = _address(arg)
                recipients = []
                self.send("250 2.1.0 OK")
            elif verb == "RCPT":
                address = _address(arg)
                if address.lower().endswith("@refused.example"):
                    self.send("550 5.1.1 no such user")
                else:
                    recipients.append(address)
                    self.send("250 2.1.5 OK")
            elif verb == "DATA":
                if sender is None or not recipients:
                    self.send("503 5.5.1 need MAIL and RCPT")
                    continue
                self.send("354 end with <CRLF>.<CRLF>")
                lines: list[bytes] = []
                while True:
                    chunk = self.rfile.readline()
                    if not chunk or chunk in (b".\r\n", b".\n"):
                        break
                    lines.append(chunk[1:] if chunk.startswith(b"..") else chunk)
                body = b"".join(lines)
                with self.store.lock:
                    self.store.submitted.append((sender, list(recipients), body))
                    local = [r for r in recipients if r in self.store.accounts]
                for _ in local[:1]:
                    self.store.put("INBOX", body)
                sender, recipients = None, []
                self.send("250 2.0.0 queued")
            elif verb == "RSET":
                sender, recipients = None, []
                self.send("250 2.0.0 OK")
            elif verb == "NOOP":
                self.send("250 2.0.0 OK")
            elif verb == "QUIT":
                self.send("221 2.0.0 bye")
                return
            else:
                self.send("502 5.5.2 unknown command")


def _address(arg: str) -> str:
    match = re.search(r"<([^>]*)>", arg)
    return match.group(1) if match else arg.split(":", 1)[-1].strip()


# --- the test interface --------------------------------------------------------------------------


def http_handler(store: Store) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def answer(self, body: Any, status: int = 200) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/_fake/state":
                self.answer(store.state())
            elif url.path == "/_fake/messages":
                name = store.name(parse_qs(url.query).get("mailbox", ["INBOX"])[0]) or "INBOX"
                with store.lock:
                    items = list(store.mailboxes[name])
                self.answer(
                    [
                        {
                            "uid": m.uid,
                            "message_id": (header_values(m.raw, "Message-ID") or [""])[0],
                            "flags": sorted(m.flags),
                        }
                        for m in items
                    ]
                )
            else:
                self.answer({"error": "not found"}, 404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length)
            if self.path == "/_fake/deliver":
                self.answer({"uid": store.put("INBOX", data)})
            elif self.path == "/_fake/reset":
                store.reset()
                self.answer({"reset": True})
            else:
                self.answer({"error": "not found"}, 404)

    return Handler


class Threaded(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


@dataclass
class Running:
    store: Store
    imap_port: int
    smtp_port: int
    http_port: int
    servers: list[socketserver.BaseServer]

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()


def start(host: str, accounts: dict[str, str], ports: tuple[int, int, int] = (0, 0, 0)) -> Running:
    """The three servers, each in a thread of its own, sharing one store."""
    store = Store(accounts)
    imap = type("Imap", (ImapHandler,), {"store": store})
    smtp = type("Smtp", (SmtpHandler,), {"store": store})
    servers: list[socketserver.BaseServer] = [
        Threaded((host, ports[0]), imap),
        Threaded((host, ports[1]), smtp),
        ThreadingHTTPServer((host, ports[2]), http_handler(store)),
    ]
    for server in servers:
        threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    imap_port, smtp_port, http_port = (s.server_address[1] for s in servers)  # type: ignore[attr-defined]
    return Running(store, imap_port, smtp_port, http_port, servers)


def accounts_from_environment() -> dict[str, str]:
    accounts: dict[str, str] = {}
    for item in os.environ.get(ACCOUNTS_VARIABLE, "").split(","):
        login, _, password = item.partition(":")
        if login and password:
            accounts[login] = password
    return accounts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A fake mail server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--imap-port", type=int, default=9143)
    parser.add_argument("--smtp-port", type=int, default=9025)
    parser.add_argument("--http-port", type=int, default=9203)
    args = parser.parse_args(argv)
    accounts = accounts_from_environment()
    if not accounts:
        sys.stderr.write(f"{ACCOUNTS_VARIABLE} is empty: no login will succeed\n")
    running = start(args.host, accounts, (args.imap_port, args.smtp_port, args.http_port))
    sys.stderr.write(
        f"{now()} fake-mail IMAP {running.imap_port} SMTP {running.smtp_port} "
        f"HTTP {running.http_port}\n"
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        running.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
