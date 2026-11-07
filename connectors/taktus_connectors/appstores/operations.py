"""How the two stores' APIs are asked, and their answers read: the builds, the beta and the
releases here; the reviews in `reviews.py`; the signing credentials in `credentials.py`.

Every call names its `platform`: `ios` is answered by the App Store Connect API under
`--app-store-target`, `android` by the Google Play Developer API (`androidpublisher` v3) under
`--play-target`. Each request carries a token signed or exchanged for this call from the
requesting identity's key (`auth.py`); the connector has no key of its own.

**Google Play works in edits.** Every reading and every change opens an edit
(`POST applications/<package>/edits`), and an edit is either committed (`:commit`) or deleted. A
reading deletes its edit; a change commits it; a change that finds nothing to do deletes it. A
failure after the edit opened deletes it, as far as the store answers.

**A Play release carries the key.** A build given to a test track and a version released on
production are a release whose `name` is the mark: `taktus-` and the first 16 hexadecimal digits
of the SHA-256 of the idempotency key. A release's name is shown in the Play Console only, never
to users. Before acting, the connector reads the track: a release with the mark is the original,
replayed, and nothing is written again. A version code already on production under another name
is a conflict: the connector never releases a version twice to production.

**Every other write is marked by the state it leaves.** App Store Connect carries no field a
write could put the key into, and a staged rollout's fraction or halt has none on either store:
a build in a beta group, a phased release's state, a rollout's fraction and a version waiting
for review are each their own mark. A state that already is what the write would make is the
original, replayed. **Weaker than a key, and stated so**: a repeat after somebody else made the
same state reports replayed too (as `deployment.workloads.scale`, ADR-0097).

How the APIs' answers map to the contract's causes:

| Answer | Cause |
|---|---|
| 400, 422: a request the store refuses | `invalid` |
| 401: the token is not admitted | `unauthenticated` |
| 403: the key's role may not do this | `forbidden` |
| 404: no such app, build, group, track or version | `not_found` |
| 409: the store's state forbids it | `conflict` |
| 429, 5xx, a refused connection | `unavailable`, retryable |
| a timeout on a change | `unknown`, effect `unknown`: a repeat reads the state again |
| any other status, a body that is not the API's | `unexpected` |
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from taktus_connectors.appstores import auth, credentials, reviews
from taktus_connectors.appstores.config import Config as Config
from taktus_connectors.serving import Call, Outcome, TargetError, invalid, unavailable

type Json = dict[str, Any]

PLATFORMS = ("ios", "android")
APPLE_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
VERSION_CODE = re.compile(r"^[1-9][0-9]{0,9}$")
TRACK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,63}$")
MAX_LIMIT = 200
MAX_PAGES = 10

LIVE = frozenset({"READY_FOR_DISTRIBUTION", "READY_FOR_SALE"})
SUBMITTABLE = frozenset(
    {
        "PREPARE_FOR_SUBMISSION",
        "READY_FOR_REVIEW",
        "REJECTED",
        "METADATA_REJECTED",
        "DEVELOPER_REJECTED",
    }
)
SUBMITTED = frozenset(
    {
        "WAITING_FOR_REVIEW",
        "IN_REVIEW",
        "ACCEPTED",
        "PENDING_DEVELOPER_RELEASE",
        "PENDING_APPLE_RELEASE",
        "PROCESSING_FOR_DISTRIBUTION",
        "PROCESSING_FOR_APP_STORE",
        *LIVE,
    }
)
REVIEW = {
    "PREPARE_FOR_SUBMISSION": "preparing",
    "READY_FOR_REVIEW": "preparing",
    "DEVELOPER_REJECTED": "preparing",
    "WAITING_FOR_EXPORT_COMPLIANCE": "preparing",
    "WAITING_FOR_REVIEW": "waiting",
    "IN_REVIEW": "in_review",
    "REJECTED": "rejected",
    "METADATA_REJECTED": "rejected",
    "INVALID_BINARY": "rejected",
    "ACCEPTED": "approved",
    "PENDING_DEVELOPER_RELEASE": "approved",
    "PENDING_APPLE_RELEASE": "approved",
    "PROCESSING_FOR_DISTRIBUTION": "approved",
    "PROCESSING_FOR_APP_STORE": "approved",
    "READY_FOR_DISTRIBUTION": "live",
    "READY_FOR_SALE": "live",
}
"""The store's word for a version, as the five words a process reads; any other is `other`."""


def _unexpected(detail: str) -> TargetError:
    return TargetError("unexpected", "none", False, detail)


def _conflict(detail: str) -> TargetError:
    return TargetError("conflict", "none", False, detail)


class _Store:
    """One call's session with one store: its address and the token signed for it."""

    def __init__(self, config: Config, call: Call, base: str, token: str) -> None:
        self.config, self.call, self.base, self.token = config, call, base.rstrip("/"), token

    async def ask(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: Json | None = None,
        writing: bool = False,
        missing: str = "no such resource",
    ) -> Any:
        self.call.count()
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            async with httpx.AsyncClient(
                base_url=self.base,
                timeout=httpx.Timeout(self.config.timeout, connect=min(10.0, self.config.timeout)),
            ) as client:
                answer = await client.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    content=None if body is None else json.dumps(body).encode("utf-8"),
                )
        except httpx.ConnectError as error:
            raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
        except httpx.TimeoutException as error:
            if writing:
                raise TargetError(
                    "unknown", "unknown", False, "the store did not answer the change in time"
                ) from error
            raise unavailable(f"the store did not answer in time: {type(error).__name__}") from (
                error
            )
        except httpx.HTTPError as error:
            # The type alone: an error's text can quote the request, the token among it.
            raise unavailable(f"the store could not be reached: {type(error).__name__}") from error
        status = answer.status_code
        if status in (200, 201):
            try:
                return answer.json()
            except ValueError as error:
                if writing:
                    raise TargetError(
                        "unknown", "unknown", False, "the store answered the change unreadably"
                    ) from error
                raise _unexpected("the store answered with a body that is not JSON") from error
        if status == 204:
            return None
        if status == 401:
            raise TargetError("unauthenticated", "none", False, "the store does not admit the key")
        if status == 403:
            raise TargetError("forbidden", "none", False, "the key's role may not do this")
        if status == 404:
            raise TargetError("not_found", "none", False, missing)
        if status == 409:
            raise _conflict("the store's state forbids the change")
        if status in (400, 422):
            raise invalid(f"the store refused the request: {status}")
        if status == 429 or status >= 500:
            raise unavailable(f"the store answered {status}")
        raise _unexpected(f"the store answered {status}, which the connector does not foresee")

    def next_page(self, document: Any) -> tuple[str, Json] | None:
        """The path and query of the next page App Store Connect names, on its own address."""
        link = ((document or {}).get("links") or {}).get("next")
        if not isinstance(link, str) or not link:
            return None
        parsed, own = urlparse(link), urlparse(self.base)
        if parsed.netloc and parsed.netloc != own.netloc:
            raise _unexpected("the store named a next page on another address")
        params: Json = dict(httpx.QueryParams(parsed.query))
        return parsed.path, params


# --- the input --------------------------------------------------------------------------------


def _platform(input: Json) -> str:
    value = input.get("platform")
    if value not in PLATFORMS:
        raise invalid("platform must be ios or android")
    return str(value)


def _app(input: Json, platform: str) -> str:
    value = input.get("app")
    pattern = APPLE_ID if platform == "ios" else PACKAGE
    if not isinstance(value, str) or pattern.match(value) is None:
        what = "an App Store Connect app's identifier" if platform == "ios" else "a package name"
        raise invalid(f"app must be {what}")
    return value


def _identifier(input: Json, field: str, platform: str) -> str:
    value = input.get(field)
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    pattern = APPLE_ID if platform == "ios" else VERSION_CODE
    if not isinstance(value, str) or pattern.match(value) is None:
        what = "the store's identifier" if platform == "ios" else "a version code"
        raise invalid(f"{field} must be {what}")
    return value


def _track(input: Json, field: str = "group") -> str:
    value = input.get(field)
    if not isinstance(value, str) or TRACK.match(value) is None:
        raise invalid(f"{field} must be a track's name")
    return value


def _fraction(input: Json) -> float:
    value = input.get("fraction")
    if isinstance(value, str):  # a run's input given on a command line arrives as text
        try:
            value = float(value)
        except ValueError:
            value = None
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value <= 1:
        raise invalid("fraction must be a number above 0 and at most 1")
    return float(value)


def _limit(input: Json, default: int = 20) -> int:
    value = input.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMIT:
        raise invalid(f"limit is a number from 1 to {MAX_LIMIT}")
    return value


async def _store(config: Config, call: Call, platform: str) -> _Store:
    if platform == "ios":
        return _Store(config, call, config.app_store_target, auth.app_store_token(call))
    token = await auth.play_token(call, config.timeout, config.token())
    return _Store(config, call, config.play_target, token)


def _mark(key: str) -> str:
    """What a Play release carries as its name: `taktus-` and the first 16 hexadecimal digits of
    the SHA-256 of the idempotency key, which never leaves Taktus. A release's name is shown in
    the Play Console only, never to the app's users."""
    return "taktus-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _write(output: Json, kind: str, identifier: str, *, replayed: bool) -> Outcome:
    record = {"kind": kind, "id": identifier}
    return Outcome(output, {"kind": "write", "replayed": replayed, "records": [record]})


# --- App Store Connect ------------------------------------------------------------------------


def _attributes(resource: Any) -> Json:
    found = (resource or {}).get("attributes") if isinstance(resource, dict) else None
    return found if isinstance(found, dict) else {}


def _related(resource: Json, name: str) -> str | None:
    data = ((resource.get("relationships") or {}).get(name) or {}).get("data")
    return str(data["id"]) if isinstance(data, dict) and data.get("id") else None


def _included(document: Any, kind: str) -> dict[str, Json]:
    items = (document or {}).get("included") or []
    return {
        str(i["id"]): i
        for i in items
        if isinstance(i, dict) and i.get("type") == kind and "id" in i
    }


def _data(document: Any) -> list[Json]:
    data = (document or {}).get("data") if isinstance(document, dict) else None
    if not isinstance(data, list):
        raise _unexpected("the store answered a list in a shape the connector does not know")
    return [d for d in data if isinstance(d, dict)]


def _version_state(resource: Json) -> str:
    attributes = _attributes(resource)
    return str(attributes.get("appVersionState") or attributes.get("appStoreState") or "")


async def _apple_versions(store: _Store, app: str, version: str | None = None) -> list[Json]:
    """The app's iOS versions, each with its phased release, newest first."""
    params: Json = {
        "filter[platform]": "IOS",
        "limit": MAX_LIMIT,
        "include": "appStoreVersionPhasedRelease",
    }
    if version is not None:
        params["filter[id]"] = version
    path = f"/v1/apps/{app}/appStoreVersions"
    found: list[Json] = []
    for _ in range(MAX_PAGES):
        document = await store.ask("GET", path, params=params, missing="no such app")
        phased = _included(document, "appStoreVersionPhasedReleases")
        for resource in _data(document):
            release = phased.get(_related(resource, "appStoreVersionPhasedRelease") or "")
            found.append({**resource, "phased": release})
        following = store.next_page(document)
        if following is None:
            break
        path, params = following
    found.sort(key=lambda r: str(_attributes(r).get("createdDate") or ""), reverse=True)
    return found


def _apple_release(app: str, resource: Json | None) -> Json:
    if resource is None:
        return {
            "platform": "ios",
            "app": app,
            "version": None,
            "id": None,
            "state": None,
            "review": "other",
            "phased": None,
            "fraction": None,
            "rolled_out": False,
        }
    state = _version_state(resource)
    release = resource.get("phased")
    phased = None
    if isinstance(release, dict):
        attributes = _attributes(release)
        phased = {
            "state": attributes.get("phasedReleaseState"),
            "day": attributes.get("currentDayNumber"),
        }
    return {
        "platform": "ios",
        "app": app,
        "version": _attributes(resource).get("versionString"),
        "id": str(resource.get("id", "")),
        "state": state,
        "review": REVIEW.get(state, "other"),
        "phased": phased,
        "fraction": None,
        "rolled_out": state in LIVE and (phased is None or phased["state"] == "COMPLETE"),
    }


async def _apple_builds(store: _Store, app: str, limit: int) -> Json:
    document = await store.ask(
        "GET",
        "/v1/builds",
        params={
            "filter[app]": app,
            "sort": "-uploadedDate",
            "limit": limit,
            "include": "preReleaseVersion",
        },
        missing="no such app",
    )
    versions = _included(document, "preReleaseVersions")
    builds = []
    for resource in _data(document)[:limit]:
        attributes = _attributes(resource)
        pre = versions.get(_related(resource, "preReleaseVersion") or "")
        builds.append(
            {
                "id": str(resource.get("id", "")),
                "version": _attributes(pre).get("version") if pre else None,
                "number": str(attributes.get("version", "")),
                "state": attributes.get("processingState"),
                "uploaded": attributes.get("uploadedDate"),
            }
        )
    return {"builds": builds, "complete": store.next_page(document) is None}


async def _apple_distribute(store: _Store, app: str, build: str, group: str) -> bool:
    """Whether the build had to be added: False when the group already holds it."""
    path = f"/v1/betaGroups/{group}/relationships/builds"
    params: Json = {"limit": MAX_LIMIT}
    for _ in range(MAX_PAGES):
        document = await store.ask("GET", path, params=params, missing="no such beta group")
        if any(str(d.get("id")) == build for d in _data(document)):
            return False
        following = store.next_page(document)
        if following is None:
            break
        path, params = following
    await store.ask(
        "POST",
        f"/v1/betaGroups/{group}/relationships/builds",
        body={"data": [{"type": "builds", "id": build}]},
        writing=True,
        missing="no such beta group or build",
    )
    return True


FEEDBACK = {
    "screenshot": "betaFeedbackScreenshotSubmissions",
    "crash": "betaFeedbackCrashSubmissions",
}
"""The two kinds of tester feedback App Store Connect keeps. Only the fields below are asked
for: never the tester, their address, their device's settings or the crash log."""


async def _apple_feedback(store: _Store, app: str, limit: int) -> Json:
    items: list[Json] = []
    complete = True
    for kind, resource_type in FEEDBACK.items():
        document = await store.ask(
            "GET",
            f"/v1/apps/{app}/{resource_type}",
            params={
                "sort": "-createdDate",
                "limit": limit,
                "include": "build",
                f"fields[{resource_type}]": "createdDate,comment,build",
                "fields[builds]": "version",
            },
            missing="no such app",
        )
        for resource in _data(document):
            attributes = _attributes(resource)
            items.append(
                {
                    "id": str(resource.get("id", "")),
                    "kind": kind,
                    "created": attributes.get("createdDate"),
                    "comment": attributes.get("comment"),
                    "build": _related(resource, "build"),
                }
            )
        complete = complete and store.next_page(document) is None
    items.sort(key=lambda i: str(i["created"] or ""), reverse=True)
    return {"feedback": items[:limit], "complete": complete and len(items) <= limit}


async def _apple_phased(store: _Store, app: str) -> Json:
    """The newest live version with a phased release; a conflict when there is none."""
    for resource in await _apple_versions(store, app):
        if _version_state(resource) in LIVE and isinstance(resource.get("phased"), dict):
            return resource
    raise _conflict("the app has no live version with a phased release")


async def _apple_set_phase(store: _Store, app: str, wanted: str) -> tuple[Json, bool]:
    resource = await _apple_phased(store, app)
    release = resource["phased"]
    current = _attributes(release).get("phasedReleaseState")
    if current == wanted:
        return resource, False
    if current == "COMPLETE" or (wanted == "PAUSED" and current != "ACTIVE"):
        raise _conflict(f"the phased release is {current}; it cannot become {wanted}")
    changed = await store.ask(
        "PATCH",
        f"/v1/appStoreVersionPhasedReleases/{release['id']}",
        body={
            "data": {
                "type": "appStoreVersionPhasedReleases",
                "id": str(release["id"]),
                "attributes": {"phasedReleaseState": wanted},
            }
        },
        writing=True,
    )
    return {**resource, "phased": (changed or {}).get("data") or release}, True


async def _apple_submit(store: _Store, app: str, version: str) -> bool:
    """Whether the version had to be submitted: False when it already waits or went further."""
    document = await store.ask(
        "GET", f"/v1/appStoreVersions/{version}", missing="no such App Store version"
    )
    resource = (document or {}).get("data")
    if not isinstance(resource, dict):
        raise _unexpected("the store answered a version in a shape the connector does not know")
    state = _version_state(resource)
    if state in SUBMITTED:
        return False
    if state not in SUBMITTABLE:
        raise _conflict(f"the version is {state or 'in no state'}; it cannot be submitted")
    open_ = await store.ask(
        "GET",
        "/v1/reviewSubmissions",
        params={
            "filter[app]": app,
            "filter[platform]": "IOS",
            "filter[state]": "READY_FOR_REVIEW,WAITING_FOR_REVIEW,IN_REVIEW",
            "include": "appStoreVersionForReview",
            "limit": MAX_LIMIT,
        },
        missing="no such app",
    )
    draft: str | None = None
    for submission in _data(open_):
        holds = _related(submission, "appStoreVersionForReview")
        state_of = _attributes(submission).get("state")
        if state_of in ("WAITING_FOR_REVIEW", "IN_REVIEW") and holds == version:
            return False
        if state_of == "READY_FOR_REVIEW":
            if holds not in (None, version):
                raise _conflict("an unsubmitted review submission holds another version")
            draft = str(submission["id"])
            if holds is None:
                await _apple_item(store, draft, version)
    if draft is None:
        made = await store.ask(
            "POST",
            "/v1/reviewSubmissions",
            body={
                "data": {
                    "type": "reviewSubmissions",
                    "attributes": {"platform": "IOS"},
                    "relationships": {"app": {"data": {"type": "apps", "id": app}}},
                }
            },
            writing=True,
            missing="no such app",
        )
        draft = str(((made or {}).get("data") or {}).get("id") or "")
        if not draft:
            raise TargetError(
                "unknown", "unknown", False, "the store answered the submission without its id"
            )
        await _apple_item(store, draft, version)
    await store.ask(
        "PATCH",
        f"/v1/reviewSubmissions/{draft}",
        body={
            "data": {"type": "reviewSubmissions", "id": draft, "attributes": {"submitted": True}}
        },
        writing=True,
    )
    return True


async def _apple_item(store: _Store, submission: str, version: str) -> None:
    await store.ask(
        "POST",
        "/v1/reviewSubmissionItems",
        body={
            "data": {
                "type": "reviewSubmissionItems",
                "relationships": {
                    "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": submission}},
                    "appStoreVersion": {"data": {"type": "appStoreVersions", "id": version}},
                },
            }
        },
        writing=True,
        missing="no such review submission or version",
    )


# --- Google Play ------------------------------------------------------------------------------


class _Edit:
    """One edit of a Play app: opened, then committed or deleted."""

    def __init__(self, store: _Store, package: str) -> None:
        self.store, self.root = store, f"/androidpublisher/v3/applications/{package}"
        self.id: str | None = None

    async def open(self) -> _Edit:
        made = await self.store.ask("POST", f"{self.root}/edits", body={}, missing="no such app")
        edit = (made or {}).get("id") if isinstance(made, dict) else None
        if not isinstance(edit, str) or not edit:
            raise _unexpected("the store opened an edit without an id")
        self.id = edit
        return self

    async def get(self, path: str, missing: str = "no such resource") -> Any:
        return await self.store.ask("GET", f"{self.root}/edits/{self.id}/{path}", missing=missing)

    async def track(self, track: str) -> Json:
        found = await self.get(f"tracks/{track}", missing=f"the app has no track {track!r}")
        if not isinstance(found, dict):
            raise _unexpected("the store answered a track in a shape the connector does not know")
        return found

    async def put_track(self, track: str, releases: list[Json]) -> None:
        await self.store.ask(
            "PUT",
            f"{self.root}/edits/{self.id}/tracks/{track}",
            body={"track": track, "releases": releases},
            missing=f"the app has no track {track!r}",
        )

    async def commit(self) -> None:
        await self.store.ask("POST", f"{self.root}/edits/{self.id}:commit", writing=True)
        self.id = None

    async def close(self) -> None:
        """Delete the edit if it is still open; a store that does not answer is left to let it
        expire, as every edit does."""
        if self.id is None:
            return
        edit, self.id = self.id, None
        try:
            await self.store.ask("DELETE", f"{self.root}/edits/{edit}")
        except TargetError:
            pass


def _releases(track: Json) -> list[Json]:
    releases = track.get("releases") or []
    return [r for r in releases if isinstance(r, dict)]


def _codes(release: Json) -> list[str]:
    return [str(c) for c in release.get("versionCodes") or []]


def _staged(track: Json) -> Json | None:
    return next((r for r in _releases(track) if r.get("status") in ("inProgress", "halted")), None)


def _play_release(app: str, track: Json) -> Json:
    releases = _releases(track)
    release = _staged(track) or next(
        (r for r in releases if r.get("status") == "completed"), releases[0] if releases else None
    )
    if release is None:
        return {
            "platform": "android",
            "app": app,
            "version": None,
            "id": None,
            "state": None,
            "review": "other",
            "phased": None,
            "fraction": None,
            "rolled_out": False,
        }
    status = release.get("status")
    fraction = 1.0 if status == "completed" else release.get("userFraction")
    return {
        "platform": "android",
        "app": app,
        "version": release.get("name"),
        "id": ",".join(_codes(release)),
        "state": status,
        "review": "other",
        "phased": None,
        "fraction": fraction,
        "rolled_out": status == "completed",
    }


async def _play_builds(store: _Store, app: str, limit: int) -> Json:
    edit = await _Edit(store, app).open()
    try:
        listed = await edit.get("bundles")
    finally:
        await edit.close()
    bundles = (listed or {}).get("bundles") if isinstance(listed, dict) else None
    if bundles is None:
        bundles = []
    if not isinstance(bundles, list):
        raise _unexpected("the store answered bundles in a shape the connector does not know")
    codes = sorted(
        (int(b["versionCode"]) for b in bundles if isinstance(b, dict) and "versionCode" in b),
        reverse=True,
    )
    builds = [
        {"id": str(c), "version": None, "number": str(c), "state": "valid", "uploaded": None}
        for c in codes[:limit]
    ]
    return {"builds": builds, "complete": len(codes) <= limit}


async def _play_change(store: _Store, app: str, track: str, change: Any) -> tuple[Json, bool]:
    """Open an edit, read the track, let `change` decide the releases to put (None: nothing to
    do), and commit or delete. Answers the track as it is after, and whether it changed."""
    edit = await _Edit(store, app).open()
    try:
        found = await edit.track(track)
        releases = change(found)
        if releases is None:
            return found, False
        await edit.put_track(track, releases)
        await edit.commit()
        return {"track": track, "releases": releases}, True
    finally:
        await edit.close()


# --- the operations ---------------------------------------------------------------------------


async def builds(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app, limit = _app(input, platform), _limit(input)
    store = await _store(config, call, platform)
    if platform == "ios":
        output = await _apple_builds(store, app, limit)
    else:
        output = await _play_builds(store, app, limit)
    return Outcome({"platform": platform, "app": app, **output}, {"kind": "read"})


async def distribute(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    build = _identifier(input, "build", platform)
    group = _identifier(input, "group", "ios") if platform == "ios" else _track(input)
    store = await _store(config, call, platform)
    if platform == "ios":
        acted = await _apple_distribute(store, app, build, group)
    else:
        mark = _mark(call.key)

        def add(track: Json) -> list[Json] | None:
            if any(r.get("name") == mark for r in _releases(track)):
                return None
            return [{"name": mark, "versionCodes": [build], "status": "completed"}]

        _, acted = await _play_change(store, app, group, add)
        output = {"platform": platform, "app": app, "build": build, "group": group}
        identifier = f"android/{app}/{group}/{build}@{mark}"
        return _write(output, "stores.beta.build", identifier, replayed=not acted)
    output = {"platform": platform, "app": app, "build": build, "group": group}
    return _write(output, "stores.beta.build", f"ios/{app}/{group}/{build}", replayed=not acted)


async def feedback(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app, limit = _app(input, platform), _limit(input, 50)
    if platform == "android":
        raise invalid("the store publishes no tester feedback through its API")
    store = await _store(config, call, platform)
    output = await _apple_feedback(store, app, limit)
    return Outcome({"platform": platform, "app": app, **output}, {"kind": "read"})


async def read_release(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    version = _identifier(input, "version", platform) if "version" in input else None
    store = await _store(config, call, platform)
    if platform == "ios":
        versions = await _apple_versions(store, app, version)
        if version is not None and not versions:
            raise TargetError("not_found", "none", False, "no such App Store version")
        return Outcome(_apple_release(app, versions[0] if versions else None), {"kind": "read"})
    edit = await _Edit(store, app).open()
    try:
        track = await edit.track("production")
    finally:
        await edit.close()
    if version is not None and not any(version in _codes(r) for r in _releases(track)):
        # A version code on no release of production is one still to submit: the store's
        # nearest word to a version in preparation (it publishes no review state).
        output = {**_play_release(app, {}), "id": version, "review": "preparing"}
        return Outcome(output, {"kind": "read"})
    return Outcome(_play_release(app, track), {"kind": "read"})


async def raise_release(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app, fraction = _app(input, platform), _fraction(input)
    store = await _store(config, call, platform)
    if platform == "ios":
        wanted = "COMPLETE" if fraction == 1 else "ACTIVE"
        resource, acted = await _apple_set_phase(store, app, wanted)
        output = {**_apple_release(app, resource), "fraction": None}
        identifier = f"ios/{app}/{resource.get('id')}@{wanted}"
        return _write(output, "stores.release.stage", identifier, replayed=not acted)

    def stage(track: Json) -> list[Json] | None:
        staged = _staged(track)
        if staged is None:
            if fraction == 1 and _releases(track):
                return None  # every release is complete: what the write would make
            raise _conflict("the production track has no staged release to raise")
        if fraction == 1:
            done = {k: v for k, v in staged.items() if k != "userFraction"}
            return [{**done, "status": "completed"}]
        if staged.get("status") == "inProgress" and staged.get("userFraction") == fraction:
            return None
        return [{**staged, "status": "inProgress", "userFraction": fraction}]

    track, acted = await _play_change(store, app, "production", stage)
    output = _play_release(app, track)
    identifier = f"android/{app}/{output['id']}@{fraction:g}"
    return _write(output, "stores.release.stage", identifier, replayed=not acted)


async def halt(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    store = await _store(config, call, platform)
    if platform == "ios":
        resource, acted = await _apple_set_phase(store, app, "PAUSED")
        identifier = f"ios/{app}/{resource.get('id')}@PAUSED"
        return _write(
            _apple_release(app, resource), "stores.release.halt", identifier, replayed=not acted
        )

    def stop(track: Json) -> list[Json] | None:
        staged = _staged(track)
        if staged is None:
            raise _conflict("the production track has no staged release to halt")
        if staged.get("status") == "halted":
            return None
        return [{**staged, "status": "halted"}]

    track, acted = await _play_change(store, app, "production", stop)
    output = _play_release(app, track)
    identifier = f"android/{app}/{output['id']}@halted"
    return _write(output, "stores.release.halt", identifier, replayed=not acted)


async def submit(config: Config, call: Call, input: Json) -> Outcome:
    platform = _platform(input)
    app = _app(input, platform)
    version = _identifier(input, "version", platform)
    fraction = _fraction(input) if "fraction" in input else None
    if platform == "ios" and fraction is not None:
        raise invalid("an App Store release takes no fraction; its phased release is the store's")
    store = await _store(config, call, platform)
    if platform == "ios":
        acted = await _apple_submit(store, app, version)
        output: Json = {"platform": platform, "app": app, "version": version, "fraction": None}
        return _write(
            output, "stores.release.submission", f"ios/{app}/{version}", replayed=not acted
        )

    mark = _mark(call.key)

    def release(track: Json) -> list[Json] | None:
        if any(r.get("name") == mark for r in _releases(track)):
            return None
        if any(version in _codes(r) for r in _releases(track)):
            raise _conflict("the version code is already released on the production track")
        if fraction is None or fraction == 1:
            return [{"name": mark, "versionCodes": [version], "status": "completed"}]
        return [
            {
                "name": mark,
                "versionCodes": [version],
                "status": "inProgress",
                "userFraction": fraction,
            }
        ]

    _, acted = await _play_change(store, app, "production", release)
    output = {"platform": platform, "app": app, "version": version, "fraction": fraction}
    return _write(
        output, "stores.release.submission", f"android/{app}/{version}", replayed=not acted
    )


OPERATIONS = {
    "stores.beta.builds": builds,
    "stores.beta.distribute": distribute,
    "stores.beta.feedback": feedback,
    "stores.releases.read": read_release,
    "stores.releases.raise": raise_release,
    "stores.releases.halt": halt,
    "stores.releases.submit": submit,
    **reviews.OPERATIONS,
    **credentials.OPERATIONS,
}
