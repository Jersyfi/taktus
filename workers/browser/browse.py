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

It imports nothing from src/taktus and nothing from the worker; the worker runs it as a command.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any
from urllib.parse import urljoin, urlparse

type Json = dict[str, Any]

TIMEOUT_MS = 15_000


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
    )
    return report


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
