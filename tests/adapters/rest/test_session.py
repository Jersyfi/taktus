"""The web app's sign-in on the HTTP surface (ADR-0119).

The account key is exchanged once for a session cookie: `HttpOnly`, `Secure`,
`SameSite=Strict`, scoped to the prefix and bounded in time. The cookie is accepted wherever
the key is, the live stream included. It ends at its time, on sign-out, and when the identity's
key is replaced. A request that changes state with it from another site is refused. Neither the
key nor the token is logged or answered in a body.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest

from taktus.adapters.driving.rest import build_app
from taktus.adapters.driving.rest.session import COOKIE

from .conftest import TENANT, Services, a_run, services

HOST = "taktus.test"
type Client = tuple[httpx.AsyncClient, Services, str]


@pytest.fixture
async def browser(prefix: str) -> AsyncIterator[Client]:
    """A client that keeps cookies as a browser does, over HTTPS: a `Secure` cookie is never
    sent over plain HTTP."""
    given = services()
    app = build_app(given, prefix=prefix)
    base = "" if prefix == "/" else prefix
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=f"https://{HOST}"
    ) as http:
        yield http, given, base


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


SAME_ORIGIN = {"Origin": f"https://{HOST}", "Sec-Fetch-Site": "same-origin"}


async def signed_in(http: httpx.AsyncClient, given: Services, base: str) -> tuple[str, str]:
    """The person signs in with their key; the key and the token of the cookie set."""
    _, key = await given.identity.person(TENANT, "idn_ada")
    answer = await http.post(f"{base}/session", headers=bearer(key))
    assert answer.status_code == 201, answer.text
    token = answer.cookies[COOKIE]
    return key, token


async def test_the_key_is_exchanged_once_for_a_cookie_the_page_cannot_read(
    browser: Client,
) -> None:
    http, given, base = browser
    _, key = await given.identity.person(TENANT, "idn_ada")
    answer = await http.post(f"{base}/session", headers=bearer(key))
    assert answer.status_code == 201
    assert answer.json()["identity"] == "idn_ada" and answer.json()["tenant"] == TENANT
    assert answer.headers["cache-control"] == "no-store"
    (cookie,) = answer.headers.get_list("set-cookie")
    name, _, rest = cookie.partition("=")
    token, *attributes = (part.strip() for part in rest.split(";"))
    assert name == COOKIE and token.startswith("tks_")
    lowered = {a.lower() for a in attributes}
    assert {"httponly", "secure", "samesite=strict", f"path={base}/"} <= lowered
    assert "max-age=43200" in lowered, "12 hours unless the operator sets another time"
    assert not any(a.startswith("domain=") for a in lowered), "this host only"
    assert token not in answer.text and key not in answer.text, "the token is in the cookie only"
    # A link opened in a new tab: the cookie alone, no key.
    runs = await http.get(f"{base}/runs")
    assert runs.status_code == 200 and runs.json()["tenant"] == TENANT


async def test_only_an_account_key_is_exchanged(browser: Client) -> None:
    http, given, base = browser
    await given.identity.person(TENANT, "idn_ada")
    for headers in ({}, bearer("tka_" + "f" * 64), {"Authorization": "Basic x"}):
        answer = await http.post(f"{base}/session", headers=headers)
        assert answer.status_code == 401
        assert "set-cookie" not in answer.headers
    assert (await http.get(f"{base}/runs")).status_code == 401


async def test_a_session_ends_at_its_time(browser: Client) -> None:
    http, given, base = browser
    await signed_in(http, given, base)
    assert (await http.get(f"{base}/runs")).status_code == 200
    given.clock.current += timedelta(hours=12)
    assert (await http.get(f"{base}/runs")).status_code == 401


async def test_signing_out_ends_the_session_and_clears_the_cookie(browser: Client) -> None:
    http, given, base = browser
    _, token = await signed_in(http, given, base)
    answer = await http.delete(f"{base}/session", headers=SAME_ORIGIN)
    assert answer.status_code == 204
    (cleared,) = answer.headers.get_list("set-cookie")
    assert cleared.startswith(f"{COOKIE}=") and "max-age=0" in cleared.lower()
    assert await given.identities.session(token) is None, "the token proves nothing any more"
    assert (await http.get(f"{base}/runs")).status_code == 401
    again = await http.get(f"{base}/runs", headers={"Cookie": f"{COOKIE}={token}"})
    assert again.status_code == 401


async def test_a_new_key_ends_every_session_of_the_identity(browser: Client) -> None:
    http, given, base = browser
    _, token = await signed_in(http, given, base)
    _, other = await given.identity.person(TENANT, "idn_bea")
    kept = await given.identities.sign_in(other)
    assert kept is not None
    await given.identities.issue_key(TENANT, "idn_ada")
    assert (await http.get(f"{base}/runs")).status_code == 401
    assert await given.identities.session(token) is None
    assert await given.identities.session(kept[0]) is not None, "another identity's stays"


async def test_a_request_that_changes_state_from_another_site_is_refused(
    browser: Client,
) -> None:
    http, given, base = browser
    await signed_in(http, given, base)
    path = f"{base}/decisions/dr_1/answer"
    for headers in (
        {},
        {"Origin": "https://elsewhere.test"},
        {"Origin": "null"},
        {"Origin": f"https://{HOST}", "Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ):
        answer = await http.post(path, json={"option": "A"}, headers=headers)
        assert answer.status_code == 403, headers
        assert answer.headers["content-type"] == "application/problem+json"
    for headers in (SAME_ORIGIN, {"Origin": f"https://{HOST}"}):
        answer = await http.post(path, json={"option": "A"}, headers=headers)
        assert answer.status_code == 404, "past the check: the request does not exist"
    # Sign-out is a change of state too.
    assert (
        await http.delete(f"{base}/session", headers={"Origin": "https://x.test"})
    ).status_code == 403
    assert (await http.get(f"{base}/runs")).status_code == 200, "still signed in"


async def test_the_bearer_key_keeps_working_and_a_token_is_read_from_the_cookie_only(
    browser: Client,
) -> None:
    http, given, base = browser
    key, token = await signed_in(http, given, base)
    http.cookies.clear()
    assert (await http.get(f"{base}/runs", headers=bearer(key))).status_code == 200
    # A client without a browser writes no Origin; with the key it needs none.
    answer = await http.post(
        f"{base}/decisions/dr_1/answer", json={"option": "A"}, headers=bearer(key)
    )
    assert answer.status_code == 404
    for headers in (
        {"Authorization": f"Session {token}"},
        bearer(token),
        {"Authorization": f"Bearer {token}", "Cookie": "other=1"},
    ):
        assert (await http.get(f"{base}/runs", headers=headers)).status_code == 401, headers
    assert (await http.get(f"{base}/runs", params={COOKIE: token})).status_code == 401


async def test_neither_the_key_nor_the_token_is_logged(
    browser: Client, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    http, given, base = browser
    caplog.set_level(logging.DEBUG)
    key, token = await signed_in(http, given, base)
    await http.get(f"{base}/runs")
    await http.post(f"{base}/decisions/dr_1/answer", json={"option": "A"})
    await http.delete(f"{base}/session", headers=SAME_ORIGIN)
    written = caplog.text + "".join(capsys.readouterr())
    assert key not in written and token not in written


async def test_the_live_stream_follows_with_the_cookie_and_ends_on_sign_out(
    browser: Client,
) -> None:
    http, given, base = browser
    await a_run(given)
    _, token = await signed_in(http, given, base)
    asked = asyncio.create_task(http.get(f"{base}/changes", params={"run": "run_1"}))
    await asyncio.sleep(0.3)  # a few heartbeats with a session that holds
    assert await given.identities.sign_out(token)
    async with asyncio.timeout(5):
        response = await asked
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    blocks = response.text.split("\n\n")
    assert blocks[1].startswith("event: snapshot")
    assert ": heartbeat" in blocks[2:]
    assert given.changes.open_streams == 0


async def test_a_browser_with_the_cookie_is_sent_to_the_report_s_page(browser: Client) -> None:
    http, given, base = browser
    await signed_in(http, given, base)
    page = await http.get(f"{base}/owner/reports/rpt_1", headers={"Accept": "text/html"})
    assert page.status_code == 303, "the page of the web app, as for a browser without a key"
