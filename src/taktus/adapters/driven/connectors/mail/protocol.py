"""How the mail connector speaks IMAP and SMTP: one session per use, the requesting identity's
password and nothing else, every fault mapped to the contract's error vocabulary.

The standard library's clients do the talking. They block, so every session runs in a thread
of its own (`asyncio.to_thread`). `security` says how a session is protected: `tls` from the
first byte, `starttls` after the greeting, or `none`. `none` sends the password in clear, and
is refused for any server that is not on this machine.

How faults map:

| Fault | Cause | Effect |
|---|---|---|
| a login refused | `unauthenticated` | `none` |
| a sender the server refuses | `forbidden` | `none` |
| a recipient or a message the server refuses for good (5xx) | `invalid` | `none` |
| no connection, a refusal for now (4xx), a timeout before handing over | `unavailable` | `none` |
| a connection lost or a timeout while the message was handed over | `unknown` | `unknown` |
| an answer the client cannot read | `unexpected` | `none` |

A fault is named by its type and its status, never by its text: a server's text can quote what
was sent, and what was sent can carry the password.
"""

from __future__ import annotations

import imaplib
import ipaddress
import re
import smtplib
import ssl
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from taktus.adapters.driven.connectors.serving import TargetError, unavailable

SECURITY = ("tls", "starttls", "none")
LOCAL_HOSTS = frozenset({"localhost"})


@dataclass(frozen=True)
class Config:
    imap_host: str
    smtp_host: str
    user: str
    """The login of the mailbox; its password is the requesting identity's credential."""
    address: str
    """The address messages are sent from."""
    imap_port: int = 993
    smtp_port: int = 587
    security: str = "tls"
    inbox: str = "INBOX"
    sent: str = "Sent"
    file_sent: bool = True
    """Whether the connector files a copy of each message it sent in the sent folder. False
    where the server files every message it accepted there itself."""
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if self.security not in SECURITY:
            raise ValueError(f"security is one of {', '.join(SECURITY)}")
        if self.security == "none":
            for host in (self.imap_host, self.smtp_host):
                if not is_local(host):
                    raise ValueError(
                        f"security none sends the password in clear; {host!r} is not this machine"
                    )

    @property
    def domain(self) -> str:
        return self.address.rsplit("@", 1)[-1]


def is_local(host: str) -> bool:
    if host in LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def quoted(text: str) -> str:
    """An IMAP quoted string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Imap:
    """One IMAP session, logged in."""

    def __init__(self, connection: imaplib.IMAP4) -> None:
        self._c = connection

    def _ok(self, answer: tuple[str, Sequence[object]], what: str) -> Sequence[object]:
        status, data = answer
        if status != "OK":
            raise TargetError("unexpected", "none", False, f"the server refused {what}")
        return data

    def select(self, mailbox: str, *, readonly: bool = True) -> None:
        status, _ = self._c.select(quoted(mailbox), readonly=readonly)
        if status != "OK":
            raise TargetError("not_found", "none", False, f"no mailbox {mailbox!r}")

    def search(self, *criteria: str) -> list[str]:
        data = self._ok(self._c.uid("SEARCH", *criteria), "a search")
        first = data[0] if data else b""
        return [uid.decode() for uid in first.split()] if isinstance(first, bytes) else []

    def by_header(self, name: str, value: str) -> list[str]:
        return self.search("HEADER", name, quoted(value))

    def fetch(self, uid: str) -> bytes:
        """The whole message, without marking it read."""
        data = self._ok(self._c.uid("FETCH", uid, "(BODY.PEEK[])"), "a fetch")
        for item in data:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
                return item[1]
        raise TargetError("not_found", "none", False, f"message {uid} has gone")

    def append(self, mailbox: str, message: bytes) -> None:
        self._ok(self._c.append(quoted(mailbox), r"(\Seen)", None, message), "filing a copy")

    def flag(self, uid: str, keyword: str) -> None:
        self._ok(self._c.uid("STORE", uid, "+FLAGS", f"({keyword})"), "setting a flag")


def _context(config: Config) -> ssl.SSLContext:
    return ssl.create_default_context()


@contextmanager
def imap(config: Config, password: str) -> Iterator[Imap]:
    """An IMAP session for the configured mailbox, logged in with the password."""
    try:
        if config.security == "tls":
            connection: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                config.imap_host,
                config.imap_port,
                ssl_context=_context(config),
                timeout=config.timeout,
            )
        else:
            connection = imaplib.IMAP4(config.imap_host, config.imap_port, timeout=config.timeout)
            if config.security == "starttls":
                connection.starttls(ssl_context=_context(config))
    except (OSError, imaplib.IMAP4.error) as error:
        raise unavailable(f"the IMAP server could not be reached: {type(error).__name__}") from None
    try:
        try:
            connection.login(config.user, password)
        except imaplib.IMAP4.error:
            raise TargetError(
                "unauthenticated", "none", False, "the IMAP server refused the login"
            ) from None
        yield Imap(connection)
    except (TimeoutError, OSError, imaplib.IMAP4.abort) as error:
        raise unavailable(f"the IMAP session broke off: {type(error).__name__}") from None
    except imaplib.IMAP4.error as error:
        raise TargetError(
            "unexpected", "none", False, f"the IMAP server answered {type(error).__name__}"
        ) from None
    finally:
        try:
            connection.logout()
        except Exception:  # noqa: S110 — the session is over either way
            pass


SMTP_CODE = re.compile(r"^\d{3}$")


def submit(config: Config, password: str, message: bytes, sender: str, to: list[str]) -> list[str]:
    """Hand one message to the SMTP server for every recipient. Returns the recipients the
    server refused while it took the message for the others: the message went out."""
    try:
        if config.security == "tls":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                config.smtp_host, config.smtp_port, timeout=config.timeout, context=_context(config)
            )
        else:
            client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=config.timeout)
            if config.security == "starttls":
                client.starttls(context=_context(config))
    except (OSError, smtplib.SMTPException) as error:
        raise unavailable(f"the SMTP server could not be reached: {type(error).__name__}") from None
    handed = False
    try:
        try:
            client.login(config.user, password)
        except smtplib.SMTPAuthenticationError:
            raise TargetError(
                "unauthenticated", "none", False, "the SMTP server refused the login"
            ) from None
        except smtplib.SMTPNotSupportedError:
            raise TargetError(
                "unexpected", "none", False, "the SMTP server offers no login"
            ) from None
        handed = True
        refused = client.sendmail(sender, to, message)
        return sorted(refused)
    except smtplib.SMTPSenderRefused as error:
        raise TargetError(
            "forbidden", "none", False, f"the server refused the sender ({error.smtp_code})"
        ) from None
    except smtplib.SMTPRecipientsRefused:
        raise TargetError("invalid", "none", False, "the server refused every recipient") from None
    except smtplib.SMTPDataError as error:
        if 400 <= error.smtp_code < 500:
            raise unavailable(f"the server deferred the message ({error.smtp_code})") from None
        raise TargetError(
            "invalid", "none", False, f"the server refused the message ({error.smtp_code})"
        ) from None
    except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as error:
        if handed:
            raise TargetError(
                "unknown",
                "unknown",
                False,
                f"the connection broke off while the message was handed over: "
                f"{type(error).__name__}",
            ) from None
        raise unavailable(f"the SMTP session broke off: {type(error).__name__}") from None
    except smtplib.SMTPResponseException as error:
        if 400 <= error.smtp_code < 500:
            raise unavailable(f"the server answered {error.smtp_code}") from None
        raise TargetError(
            "unexpected", "none", False, f"the server answered {error.smtp_code}"
        ) from None
    finally:
        try:
            client.quit()
        except Exception:  # noqa: S110 — the session is over either way
            pass
