"""The browser worker's step, `workers/browser/browse.py`, in headless Chromium (ADR-0218).

A served page is checked: a flow typed and clicked, a text expected and one that must be absent,
a request to a host the check does not name refused inside the browser, and a credential typed
by its name without its value reaching the report. The contract around the steps is the
conformance suite's (`tests/conformance/test_worker_v1_browser.py`).
"""

from __future__ import annotations

import contextlib
import functools
import importlib.util
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BROWSE = ROOT / "workers" / "browser" / "browse.py"
WORKER = ROOT / "workers" / "browser" / "worker.py"
PAGE = b"""<!doctype html><html><head><title>Sign in</title></head><body>
<h1>Sign in</h1><input id="user"><input id="password" type="password">
<button id="go" type="button" onclick="document.getElementById('out').textContent =
document.getElementById('password').value.length > 0 ? 'Welcome' : 'Denied'">Go</button>
<p id="out"></p><img src="http://tracker.invalid/pixel.gif"></body></html>"""


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def site(tmp_path: Path) -> Iterator[str]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
    except Exception as error:
        pytest.skip(f"the browser worker needs its driver and Chromium: {error}")
    (tmp_path / "index.html").write_bytes(PAGE)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()
    server.server_close()


def browse(check: dict[str, Any], **env: str) -> dict[str, Any]:
    done = subprocess.run(  # noqa: S603 — our own script, fixed arguments
        [sys.executable, str(BROWSE), json.dumps(check)],
        capture_output=True,
        check=True,
        timeout=60,
        env={**os.environ, **env},
    )
    report: dict[str, Any] = json.loads(done.stdout)
    return report


def test_a_flow_is_typed_and_clicked_and_its_answer_read(site: str) -> None:
    secret = "typed-value-never-shown"  # noqa: S105 — a test value, not a credential
    report = browse(
        {
            "url": site,
            "steps": [
                {"fill": "#user", "value": "test-user"},
                {"fill": "#password", "value_env": "TEST_PASSWORD"},
                {"click": "#go"},
            ],
            "expect": ["Welcome"],
            "absent": ["Denied"],
        },
        TEST_PASSWORD=secret,
    )
    assert report["passed"] is True, report
    assert report["status"] == 200 and report["title"] == "Sign in"
    assert report["expected"] == {"Welcome": True} and report["absent"] == {"Denied": False}
    assert secret not in json.dumps(report), "a credential is typed, never reported"


def test_a_host_the_check_does_not_name_is_refused_inside_the_browser(site: str) -> None:
    report = browse({"url": site, "expect": ["Sign in"]})
    assert report["blocked"] == ["tracker.invalid"]
    assert report["passed"] is True, "a refused request is named, and the page still holds"


def test_a_check_that_does_not_hold_is_a_finding_not_a_failure(site: str) -> None:
    report = browse({"url": site, "expect": ["Dashboard"], "steps": [{"click": "#missing"}]})
    assert report["passed"] is False
    assert report["expected"] == {"Dashboard": False}
    assert report["steps"][0]["done"] is False and "error" in report["steps"][0]


def test_the_worker_declares_browser_check_and_plans_a_step_per_check() -> None:
    listed = subprocess.run(  # noqa: S603 — our own script, fixed arguments
        [sys.executable, str(WORKER), "--list-faults"], capture_output=True, check=True, timeout=30
    )
    assert b"W-07" in listed.stdout, "the reference worker's faults, kept"


def test_the_last_step_gathers_every_check_and_names_each_that_failed() -> None:
    spec = importlib.util.spec_from_file_location("browser_worker", WORKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module.work_for(
        {"inputs": {"checks": [{"url": "http://a.example/"}, {"url": "http://b.example/x"}]}},
        "quick",
        None,
    )
    assert [s.step_id for s in plan] == ["check-1", "check-2", "report"]
    assert module.hosts_of({"inputs": {"checks": [{"url": "http://a.example/"}]}}) == ["a.example"]
    gathered = json.loads(
        module.gathered([b'{"name": "one", "passed": true}', b'{"name": "two", "passed": false}'])
    )
    assert (gathered["count"], gathered["passed"], gathered["failures"]) == (2, 1, ["two"])


# --- the passive security check (B-7.09) ------------------------------------------------------

PROTECTED = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
START = b"<!doctype html><title>App</title><body>App ref: refs/heads/main</body>"
"""An application's start page, which it answers every unknown path with."""


@contextlib.contextmanager
def serving(headers: dict[str, str], files: dict[str, bytes], cookie: str) -> Iterator[str]:
    """A page answered with the headers given and a cookie set, and files at well-known paths;
    every other path answers with the start page, as a single-page application does."""

    class Handler(Quiet):
        def version_string(self) -> str:
            return "app"  # the `Server` header, without the version Python would name

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            body = files.get(path, START)
            self.send_response(200)
            for name, value in headers.items():
                self.send_header(name, value)
            if path == "/":
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()


def test_a_passive_security_check_names_missing_headers_weak_cookies_and_an_exposed_path(
    site: str,
) -> None:
    exposed = {"/.git/HEAD": b"ref: refs/heads/main\n"}
    with serving({"Server": "web/2.4.1"}, exposed, "sid=abc123; Path=/") as url:
        report = browse({"url": url, "security": True})
    security = report["security"]
    assert report["passed"] is False
    assert security["https"] is False
    assert "the page is not served over TLS" in security["findings"]
    assert set(security["headers_missing"]) == {
        "content-security-policy",
        "x-content-type-options",
        "referrer-policy",
        "x-frame-options",
    }
    assert security["disclosed"] == ["server"]
    assert security["cookies"] == [{"name": "sid", "lacks": ["Secure", "HttpOnly"]}]
    assert security["exposed"] == ["/.git/HEAD"]
    assert "abc123" not in json.dumps(report), "a cookie's value is never reported"
    assert "refs/heads" not in json.dumps(report), "what a path exposes is never reported"


def test_a_page_that_answers_every_path_with_itself_exposes_nothing_and_its_headers_hold(
    site: str,
) -> None:
    with serving(PROTECTED, {}, "sid=abc123; Path=/; HttpOnly; Secure") as url:
        report = browse({"url": url, "security": True})
    security = report["security"]
    assert security["exposed"] == [], "a start page served for every path matches no signature"
    assert security["headers_missing"] == []
    assert security["disclosed"] == []
    assert security["findings"] == ["the page is not served over TLS"]


def test_the_task_makes_every_check_a_security_check() -> None:
    spec = importlib.util.spec_from_file_location("browser_worker", WORKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task = {"inputs": {"checks": [{"url": "https://a.example/"}], "security": True}}
    plan = module.work_for(task, "quick", None)
    assert '"security": true' in plan[0].command
