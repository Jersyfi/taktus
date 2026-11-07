#!/usr/bin/env python3
"""One check of a web page in headless Chromium, driven by Playwright: the browser worker's step.

It takes the check as a JSON document in its first argument and prints its report as one JSON
document. A check names a `url`, and may name `expect` (texts the page must show), `absent`
(texts it must not show), `steps` (what is done on the page before it is read: `click` a
selector, `fill` a selector with a value, `press` a key, `goto` another path, `wait` for a
selector) and `status` (the HTTP status the page must answer with, by default below 400). A
`fill` may name `value_env` in place of `value`: the credential whose value it types, which is
never printed.

The page reaches only the hosts the check names in `hosts`; every other request is aborted and
named in the report. That is how the worker's frame holds inside the browser: the worker held
each of those hosts against `allowed_hosts` before this step ran (contracts/worker/v1 W-13).

The report names what was asked and what was found: the status, the title, each expected text
found or not, each absent text seen or not, the console's errors, the requests that failed or
were aborted, the digest of the page's visible text and of a screenshot, and `passed`. A check
that does not hold is a finding, not a failure of the step: the script exits 0. It exits 2 only
where the browser itself could not run.

A check that names `security: true` is also a passive security check of the page (B-7.09):
whether it was served over TLS, which of the response headers a browser protects a page with are
missing, which headers name the server's software, which cookies lack `Secure` or `HttpOnly`,
and which of a fixed list of well-known paths answers with the content its name promises (a
repository's `HEAD`, an environment file, a private key). Each path is one GET; what it answers
is matched against its signature and never reported, so a secret it exposes is not copied
anywhere. Nothing is sent that a browser would not send: no payload, no form, no guessed
identifier. Every finding makes the check not pass.

It imports nothing from src/taktus and nothing from the worker; the worker runs it as a command.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any
from urllib.parse import urljoin, urlparse

type Json = dict[str, Any]

TIMEOUT_MS = 15_000

PROTECTING = (
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "referrer-policy",
)
"""The response headers a browser protects a page with, each missing one a finding. Framing is
judged apart: `x-frame-options`, or a content security policy naming `frame-ancestors`."""

DISCLOSING = ("x-powered-by", "x-aspnet-version", "x-aspnetmvc-version")
"""Headers that name the server's software; `server` counts only where it carries a version."""

EXPOSED: tuple[tuple[str, str], ...] = (
    ("/.git/HEAD", r"^ref: refs/"),
    ("/.git/config", r"^\[core\]"),
    ("/.env", r"(?m)^[A-Z][A-Z0-9_]*=\S"),
    ("/.svn/entries", r"^\d+\s*$|^<\?xml[^>]*>\s*<wc-entries"),
    ("/.htpasswd", r"(?m)^[^:\s]+:(\$apr1\$|\$2[aby]\$|\{SHA\})"),
    ("/.aws/credentials", r"(?m)^aws_access_key_id\s*="),
    ("/id_rsa", r"-----BEGIN (OPENSSH|RSA) PRIVATE KEY-----"),
    ("/server-status", r"Apache Server Status"),
    ("/phpinfo.php", r"<title>phpinfo\(\)</title>|PHP Version \d"),
    ("/.DS_Store", r"^\x00\x00\x00\x01Bud1"),
)
"""The fixed list of well-known paths, each with the signature of what it would expose. A path
counts as exposed only when it answers 200 and its content matches: an application that answers
every path with its own start page exposes nothing by that."""


def run(check: Json) -> Json:
    from playwright.sync_api import Error, sync_playwright

    url = str(check["url"])
    hosts = {str(h) for h in check.get("hosts", [])} | {urlparse(url).hostname or ""}
    report: Json = {
        "name": check.get("name") or url,
        "url": url,
        "status": None,
        "title": None,
        "expected": {},
        "absent": {},
        "console_errors": [],
        "failed_requests": [],
        "blocked": [],
        "steps": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(ignore_https_errors=False)
            page = context.new_page()

            def route(request_route: Any) -> None:
                host = urlparse(request_route.request.url).hostname or ""
                if host in hosts:
                    request_route.continue_()
                else:
                    report["blocked"].append(host)
                    request_route.abort()

            page.route("**/*", route)
            page.on(
                "console",
                lambda message: (
                    report["console_errors"].append(message.text)
                    if message.type == "error"
                    else None
                ),
            )
            page.on(
                "requestfailed",
                lambda request: report["failed_requests"].append(urlparse(request.url).path),
            )
            response = page.goto(url, timeout=TIMEOUT_MS, wait_until="load")
            report["status"] = None if response is None else response.status
            if check.get("security") is True:
                report["security"] = _security(context, response, url)
            for step in check.get("steps", []):
                report["steps"].append(_act(page, step, url))
            text = page.inner_text("body", timeout=TIMEOUT_MS)
            report["title"] = page.title()
            report["expected"] = {t: t in text for t in check.get("expect", [])}
            report["absent"] = {t: t in text for t in check.get("absent", [])}
            report["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            report["screenshot_sha256"] = hashlib.sha256(
                page.screenshot(full_page=True)
            ).hexdigest()
        except Error as error:
            report["error"] = str(error).splitlines()[0][:300]
        finally:
            browser.close()
    report["blocked"] = sorted(set(report["blocked"]))
    wanted = check.get("status")
    status_holds = report["status"] is not None and (
        report["status"] == wanted if isinstance(wanted, int) else report["status"] < 400
    )
    report["passed"] = bool(
        "error" not in report
        and status_holds
        and all(report["expected"].values())
        and not any(report["absent"].values())
        and all(s.get("done") for s in report["steps"])
        and not (report.get("security") or {}).get("findings")
    )
    return report


def _security(context: Any, response: Any, url: str) -> Json:
    """What the page's answer says about its own protection, passively: TLS, headers, cookie
    flags, and the fixed list of well-known paths. Never a header's or a cookie's value, never
    what an exposed path holds."""
    findings: list[str] = []
    https = urlparse(url).scheme == "https"
    details = None if response is None else response.security_details()
    tls = (details or {}).get("protocol") if https else None
    if not https:
        findings.append("the page is not served over TLS")
    headers = {} if response is None else {k.lower(): v for k, v in response.all_headers().items()}
    missing = [name for name in PROTECTING if name not in headers]
    if not https:
        # HSTS is only honoured over TLS; its absence is the finding above.
        missing = [m for m in missing if m != "strict-transport-security"]
    policy = headers.get("content-security-policy", "")
    if "x-frame-options" not in headers and "frame-ancestors" not in policy:
        missing.append("x-frame-options")
    findings += [f"the header {name} is missing" for name in missing]
    disclosed = [name for name in DISCLOSING if name in headers]
    if re.search(r"\d", headers.get("server", "")):
        disclosed.append("server")
    findings += [f"the header {name} names the server's software" for name in disclosed]
    cookies = []
    for cookie in context.cookies(url):
        flags = (("Secure", cookie.get("secure")), ("HttpOnly", cookie.get("httpOnly")))
        lacking = [flag for flag, held in flags if not held]
        if lacking:
            cookies.append({"name": cookie.get("name"), "lacks": lacking})
            findings.append(f"the cookie {cookie.get('name')} lacks {' and '.join(lacking)}")
    from playwright.sync_api import Error

    exposed = []
    for path, signature in EXPOSED:
        try:
            answer = context.request.get(
                urljoin(url, path), timeout=TIMEOUT_MS, max_redirects=0, fail_on_status_code=False
            )
            body = answer.body() if answer.status == 200 else b""
        except Error:
            body = b""  # a path that cannot be read exposes nothing
        if body and re.search(signature, body[:4096].decode("latin-1")):
            exposed.append(path)
            findings.append(f"the path {path} answers with what its name promises")
    return {
        "https": https,
        "tls": tls,
        "headers_missing": missing,
        "disclosed": disclosed,
        "cookies": cookies,
        "exposed": exposed,
        "findings": findings,
    }


def _act(page: Any, step: Json, base: str) -> Json:
    """One action on the page, and whether it was done; a step that cannot be done is named."""
    from playwright.sync_api import Error

    kind = next((k for k in ("click", "fill", "press", "goto", "wait") if k in step), None)
    done: Json = {"action": kind, "done": False}
    try:
        if kind == "click":
            page.click(str(step["click"]), timeout=TIMEOUT_MS)
        elif kind == "fill":
            # A credential arrives by its name in the environment and is typed, never printed.
            secret = step.get("value_env")
            value = os.environ.get(str(secret), "") if secret else str(step.get("value", ""))
            page.fill(str(step["fill"]), value, timeout=TIMEOUT_MS)
        elif kind == "press":
            page.keyboard.press(str(step["press"]))
        elif kind == "goto":
            page.goto(urljoin(base, str(step["goto"])), timeout=TIMEOUT_MS, wait_until="load")
        elif kind == "wait":
            page.wait_for_selector(str(step["wait"]), timeout=TIMEOUT_MS)
        else:
            done["error"] = "an action is one of click, fill, press, goto, wait"
            return done
        page.wait_for_load_state("load", timeout=TIMEOUT_MS)
        done["done"] = True
    except Error as error:
        done["error"] = str(error).splitlines()[0][:300]
    return done


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: browse.py '<check as JSON>'", file=sys.stderr)
        return 2
    check = json.loads(argv[1])
    try:
        report = run(check)
    except Exception as error:
        print(f"the browser could not run: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
