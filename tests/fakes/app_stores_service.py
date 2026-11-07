#!/usr/bin/env python3
"""A fake of the two app stores' APIs the app stores connector uses: the App Store Connect API
and the Google Play Developer API (`androidpublisher` v3), with Google's OAuth 2.0 token
endpoint, in memory, on one address.

The connector under `connectors/taktus_connectors/appstores/` asks:

- App Store Connect, JSON:API documents under `/v1/`: `GET builds?filter[app]=..&sort=..&include=
  preReleaseVersion`; `GET` and `POST betaGroups/<id>/relationships/builds`; `GET apps/<id>/
  betaFeedbackScreenshotSubmissions` and `.../betaFeedbackCrashSubmissions`, honouring
  `fields[...]`; `GET apps/<id>/appStoreVersions?filter[platform]=IOS&include=
  appStoreVersionPhasedRelease`; `GET appStoreVersions/<id>`; `PATCH
  appStoreVersionPhasedReleases/<id>`; `GET`, `POST` and `PATCH reviewSubmissions`, `POST
  reviewSubmissionItems`. A list carries `links.next` while more pages follow (`limit`, at most
  200, and a `cursor`).
- Google Play under `/androidpublisher/v3/applications/<package>/`: `POST edits`, `DELETE
  edits/<id>`, `GET edits/<id>/bundles`, `GET` and `PUT edits/<id>/tracks/<track>`, `POST
  edits/<id>:commit`. An edit is a copy of the app's tracks; only a commit makes it the app's.
- `POST /token`: a service account's signed assertion exchanged for an access token.

What it enforces, because the connector's checks depend on it:

- **Authentication.** It is started with keys (`FAKE_TOKENS`: one key, a JSON object with
  `ios` and `android` members, the way `STORES_KEY` holds them). An App Store Connect request
  needs an ES256 token signed by the `ios` key, its `kid` the key's identifier, `iss` the
  issuer, `aud` `appstoreconnect-v1`, at most twenty minutes long. `POST /token` admits an
  RS256 assertion signed by the `android` key, `iss` its `client_email`, `aud` ending in
  `/token`, the Play scope; a Play request needs a token it issued. Otherwise 401.
- **A track's releases as Play keeps them.** A `PUT` names the desired releases: a `completed`
  one replaces every release of the track; a staged one (`inProgress`, `halted`) replaces the
  staged one and keeps the newest completed. `userFraction` only on a staged release, strictly
  between 0 and 1; otherwise 400.
- **A phased release's states.** `ACTIVE` and `PAUSED` turn into each other; either becomes
  `COMPLETE`; a `COMPLETE` one changes no more (409).
- **A review submission.** One unsubmitted submission per app; `submitted: true` puts it and its
  version in `WAITING_FOR_REVIEW`.

The iOS app `1000000001` has the builds `b-1` (1.0, number 1) and `b-2` (1.1, number 2), both
`VALID`; the beta group `g-1`, empty; the live version `v-10` (1.0) with a phased release `pr-10`
`ACTIVE` on day 3; the version `v-11` (1.1) `PREPARE_FOR_SUBMISSION`; one screenshot feedback on
`b-2` and one crash feedback on `b-1`, each with a tester's address. The Android package
`com.example.app` has the bundles 1 and 2, the track `internal` empty and `production` with
version code 1 completed. Test-only: `GET /_fake/state`; `POST /_fake/reset`; `POST
/_fake/review {"version": <id>, "state": <word>}` sets a version's state as the review would;
`POST /_fake/verdict` with the same body sets the state a version lands in once it is submitted.
Runnable as `python3 tests/fakes/app_stores_service.py --port 9240`.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization

type Json = dict[str, Any]

APP = "1000000001"
PACKAGE = "com.example.app"
PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
ROOT = f"/androidpublisher/v3/applications/{PACKAGE}"


def seed() -> Json:
    return {
        "builds": [
            {"id": "b-1", "number": "1", "pre": "p-10", "uploaded": "2026-10-01T08:00:00Z"},
            {"id": "b-2", "number": "2", "pre": "p-11", "uploaded": "2026-11-01T08:00:00Z"},
        ],
        "pre": {"p-10": "1.0", "p-11": "1.1"},
        "groups": {"g-1": []},
        "versions": {
            "v-10": {
                "versionString": "1.0",
                "state": "READY_FOR_DISTRIBUTION",
                "createdDate": "2026-10-02T08:00:00Z",
                "phased": "pr-10",
            },
            "v-11": {
                "versionString": "1.1",
                "state": "PREPARE_FOR_SUBMISSION",
                "createdDate": "2026-11-02T08:00:00Z",
                "phased": None,
            },
        },
        "phased": {"pr-10": {"phasedReleaseState": "ACTIVE", "currentDayNumber": 3}},
        "submissions": {},
        "verdicts": {},
        "feedback": {
            "betaFeedbackScreenshotSubmissions": [
                {
                    "id": "fs-1",
                    "build": "b-2",
                    "attributes": {
                        "createdDate": "2026-11-03T09:00:00Z",
                        "comment": "The button is cut off",
                        "email": "tester@example.com",
                        "deviceModel": "iPhone15,2",
                    },
                },
            ],
            "betaFeedbackCrashSubmissions": [
                {
                    "id": "fc-1",
                    "build": "b-1",
                    "attributes": {
                        "createdDate": "2026-10-04T09:00:00Z",
                        "comment": "It closed on start",
                        "email": "other@example.com",
                        "crashLog": "...",
                    },
                },
            ],
        },
        "bundles": [1, 2],
        "tracks": {
            "internal": [],
            "production": [{"name": "1.0", "versionCodes": ["1"], "status": "completed"}],
        },
        "edits": {},
    }


class State:
    def __init__(self, keys: set[str]) -> None:
        self.lock = threading.Lock()
        self.keys = [json.loads(k) for k in keys]
        self.issued: set[str] = set()
        self.data = seed()
        self.requests = 0

    def apple_admits(self, token: str) -> bool:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            return False
        for key in self.keys:
            ios = key.get("ios") or {}
            if not ios or header.get("kid") != ios.get("key_id") or header.get("alg") != "ES256":
                continue
            public = serialization.load_pem_private_key(
                ios["private_key"].encode(), None
            ).public_key()
            try:
                claims = jwt.decode(
                    token,
                    public,
                    algorithms=["ES256"],
                    audience="appstoreconnect-v1",
                    issuer=ios["issuer_id"],
                )
            except jwt.PyJWTError:
                return False
            return int(claims["exp"]) - int(claims["iat"]) <= 1200
        return False

    def exchange(self, assertion: str) -> str | None:
        try:
            unverified = jwt.decode(assertion, options={"verify_signature": False})
        except jwt.PyJWTError:
            return None
        for key in self.keys:
            android = key.get("android") or {}
            if not android or android.get("client_email") != unverified.get("iss"):
                continue
            public = serialization.load_pem_private_key(
                android["private_key"].encode(), None
            ).public_key()
            try:
                claims = jwt.decode(
                    assertion,
                    public,
                    algorithms=["RS256"],
                    audience=str(unverified.get("aud", "")),
                )
            except jwt.PyJWTError:
                return None
            if not str(claims.get("aud", "")).endswith("/token"):
                return None
            if PLAY_SCOPE not in str(claims.get("scope", "")).split():
                return None
            token = "ya29.fake-" + secrets.token_hex(12)
            self.issued.add(token)
            return token
        return None


def _put(track: list[Json], releases: list[Json]) -> list[Json] | None:
    result = copy.deepcopy(track)
    for release in releases:
        status = release.get("status")
        fraction = release.get("userFraction")
        if status not in ("draft", "inProgress", "halted", "completed"):
            return None
        if fraction is not None and (
            status not in ("inProgress", "halted") or not 0 < fraction < 1
        ):
            return None
        if status == "inProgress" and fraction is None:
            return None
        if status == "completed":
            result = [copy.deepcopy(release)]
        else:
            completed = [r for r in result if r.get("status") == "completed"][-1:]
            result = [*completed, copy.deepcopy(release)]
    return result


def handler(state: State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def answer(self, status: int, body: Any = None) -> None:
            data = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error(self, status: int, title: str) -> None:
            self.answer(status, {"errors": [{"status": str(status), "title": title}]})

        def body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if self.headers.get("Content-Type", "").startswith("application/x-www-form"):
                return {k: v[0] for k, v in parse_qs(raw.decode()).items()}
            return json.loads(raw) if raw else None

        def base(self) -> str:
            return f"http://{self.headers.get('Host', '127.0.0.1')}"

        def admitted(self, path: str) -> bool:
            given = self.headers.get("Authorization", "")
            token = given.removeprefix("Bearer ") if given.startswith("Bearer ") else ""
            if path.startswith("/v1/"):
                return state.apple_admits(token)
            return token in state.issued

        def do_GET(self) -> None:
            self.route("GET")

        def do_POST(self) -> None:
            self.route("POST")

        def do_PUT(self) -> None:
            self.route("PUT")

        def do_PATCH(self) -> None:
            self.route("PATCH")

        def do_DELETE(self) -> None:
            self.route("DELETE")

        def route(self, method: str) -> None:
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            path = url.path
            with state.lock:
                if path.startswith("/_fake/"):
                    self.fake(method, path)
                    return
                state.requests += 1
                if path == "/token" and method == "POST":
                    form = self.body() or {}
                    token = state.exchange(str(form.get("assertion", "")))
                    if token is None:
                        self.answer(400, {"error": "invalid_grant"})
                        return
                    self.answer(
                        200, {"access_token": token, "expires_in": 3599, "token_type": "Bearer"}
                    )
                    return
                if not self.admitted(path):
                    self.error(401, "NOT_AUTHORIZED")
                    return
                if path.startswith("/v1/"):
                    self.apple(method, path, query)
                elif path.startswith("/androidpublisher/v3/applications/"):
                    self.play(method, path)
                else:
                    self.error(404, "NOT_FOUND")

        # --- test-only -----------------------------------------------------------------------

        def fake(self, method: str, path: str) -> None:
            data = state.data
            if path == "/_fake/state" and method == "GET":
                self.answer(
                    200,
                    {
                        "ios": {
                            "groups": data["groups"],
                            "versions": {k: v["state"] for k, v in data["versions"].items()},
                            "phased": {
                                "state": data["phased"]["pr-10"]["phasedReleaseState"],
                                "day": data["phased"]["pr-10"]["currentDayNumber"],
                            },
                            "submissions": {k: v["state"] for k, v in data["submissions"].items()},
                        },
                        "android": {"tracks": data["tracks"]},
                        "edits_open": len(data["edits"]),
                        "requests": state.requests,
                    },
                )
            elif path == "/_fake/reset" and method == "POST":
                state.data = seed()
                self.answer(200, {"reset": True})
            elif path == "/_fake/verdict" and method == "POST":
                given = self.body() or {}
                data["verdicts"][str(given.get("version"))] = str(given.get("state"))
                self.answer(200, {"queued": True})
            elif path == "/_fake/review" and method == "POST":
                given = self.body() or {}
                version = data["versions"].get(given.get("version"))
                if version is None:
                    self.answer(404, {"error": "no such version"})
                    return
                version["state"] = str(given.get("state"))
                self.answer(200, {"state": version["state"]})
            else:
                self.answer(404, {"error": "unknown"})

        # --- App Store Connect ---------------------------------------------------------------

        def page(self, items: list[Json], query: dict[str, str], path: str, **extra: Any) -> None:
            limit = min(int(query.get("limit", "50")), 200)
            start = int(query.get("cursor", "0"))
            body: Json = {"data": items[start : start + limit], "links": {"self": self.path}}
            if start + limit < len(items):
                body["links"]["next"] = f"{self.base()}{path}?limit={limit}&cursor={start + limit}"
            body["meta"] = {"paging": {"total": len(items), "limit": limit}}
            body.update(extra)
            self.answer(200, body)

        def version(self, vid: str) -> Json:
            v = state.data["versions"][vid]
            resource: Json = {
                "type": "appStoreVersions",
                "id": vid,
                "attributes": {
                    "platform": "IOS",
                    "versionString": v["versionString"],
                    "appVersionState": v["state"],
                    "appStoreState": v["state"],
                    "createdDate": v["createdDate"],
                },
                "relationships": {
                    "appStoreVersionPhasedRelease": {
                        "data": {"type": "appStoreVersionPhasedReleases", "id": v["phased"]}
                        if v["phased"]
                        else None
                    }
                },
            }
            return resource

        def phased(self, pid: str) -> Json:
            return {
                "type": "appStoreVersionPhasedReleases",
                "id": pid,
                "attributes": dict(state.data["phased"][pid]),
            }

        def apple(self, method: str, path: str, query: dict[str, str]) -> None:
            data = state.data
            parts = path.strip("/").split("/")[1:]
            if method == "GET" and parts == ["builds"]:
                if query.get("filter[app]") != APP:
                    self.page([], query, path)
                    return
                builds = sorted(
                    data["builds"],
                    key=lambda b: b["uploaded"],
                    reverse=query.get("sort") == "-uploadedDate",
                )
                items = [
                    {
                        "type": "builds",
                        "id": b["id"],
                        "attributes": {
                            "version": b["number"],
                            "uploadedDate": b["uploaded"],
                            "processingState": "VALID",
                        },
                        "relationships": {
                            "preReleaseVersion": {
                                "data": {"type": "preReleaseVersions", "id": b["pre"]}
                            }
                        },
                    }
                    for b in builds
                ]
                included = (
                    [
                        {
                            "type": "preReleaseVersions",
                            "id": p,
                            "attributes": {"version": v, "platform": "IOS"},
                        }
                        for p, v in data["pre"].items()
                    ]
                    if "preReleaseVersion" in query.get("include", "")
                    else []
                )
                self.page(items, query, path, included=included)
            elif (
                len(parts) == 4
                and parts[0] == "betaGroups"
                and parts[2:]
                == [
                    "relationships",
                    "builds",
                ]
            ):
                group = data["groups"].get(parts[1])
                if group is None:
                    self.error(404, "NOT_FOUND")
                elif method == "GET":
                    self.page([{"type": "builds", "id": b} for b in group], query, path)
                elif method == "POST":
                    given = (self.body() or {}).get("data") or []
                    known = {b["id"] for b in data["builds"]}
                    if not given or any(d.get("id") not in known for d in given):
                        self.error(404, "NOT_FOUND")
                        return
                    for d in given:
                        if d["id"] not in group:
                            group.append(d["id"])
                    self.answer(204)
                else:
                    self.error(405, "METHOD_NOT_ALLOWED")
            elif method == "GET" and len(parts) == 3 and parts[0] == "apps":
                if parts[1] != APP:
                    self.error(404, "NOT_FOUND")
                elif parts[2] in data["feedback"]:
                    self.feedback(parts[2], query, path)
                elif parts[2] == "appStoreVersions":
                    if query.get("filter[platform]") not in (None, "IOS"):
                        self.page([], query, path)
                        return
                    wanted = query.get("filter[id]")
                    ids = [v for v in data["versions"] if wanted in (None, v)]
                    items = [self.version(v) for v in ids]
                    pids = [data["versions"][v]["phased"] for v in ids]
                    included = (
                        [self.phased(p) for p in pids if p]
                        if ("appStoreVersionPhasedRelease" in query.get("include", ""))
                        else []
                    )
                    self.page(items, query, path, included=included)
                else:
                    self.error(404, "NOT_FOUND")
            elif method == "GET" and len(parts) == 2 and parts[0] == "appStoreVersions":
                if parts[1] not in data["versions"]:
                    self.error(404, "NOT_FOUND")
                    return
                self.answer(200, {"data": self.version(parts[1])})
            elif (
                method == "PATCH"
                and len(parts) == 2
                and parts[0] == "appStoreVersionPhasedReleases"
            ):
                release = data["phased"].get(parts[1])
                if release is None:
                    self.error(404, "NOT_FOUND")
                    return
                wanted = (((self.body() or {}).get("data") or {}).get("attributes") or {}).get(
                    "phasedReleaseState"
                )
                current = release["phasedReleaseState"]
                if wanted not in ("ACTIVE", "PAUSED", "COMPLETE"):
                    self.error(422, "ENTITY_ERROR")
                    return
                if current == "COMPLETE" or (wanted == "PAUSED" and current != "ACTIVE"):
                    self.error(409, "STATE_ERROR")
                    return
                release["phasedReleaseState"] = wanted
                self.answer(200, {"data": self.phased(parts[1])})
            elif parts and parts[0] == "reviewSubmissions":
                self.submissions(method, parts, query, path)
            elif method == "POST" and parts == ["reviewSubmissionItems"]:
                rel = ((self.body() or {}).get("data") or {}).get("relationships") or {}
                sid = ((rel.get("reviewSubmission") or {}).get("data") or {}).get("id")
                vid = ((rel.get("appStoreVersion") or {}).get("data") or {}).get("id")
                submission = data["submissions"].get(sid)
                if submission is None or vid not in data["versions"]:
                    self.error(404, "NOT_FOUND")
                    return
                if submission["state"] != "READY_FOR_REVIEW" or submission["version"]:
                    self.error(409, "STATE_ERROR")
                    return
                submission["version"] = vid
                self.answer(201, {"data": {"type": "reviewSubmissionItems", "id": f"i-{sid}"}})
            else:
                self.error(404, "NOT_FOUND")

        def feedback(self, kind: str, query: dict[str, str], path: str) -> None:
            fields = query.get(f"fields[{kind}]")
            wanted = set(fields.split(",")) if fields else None
            items = []
            for f in sorted(
                state.data["feedback"][kind],
                key=lambda f: f["attributes"]["createdDate"],
                reverse=query.get("sort") == "-createdDate",
            ):
                attributes = {
                    k: v for k, v in f["attributes"].items() if wanted is None or k in wanted
                }
                items.append(
                    {
                        "type": kind,
                        "id": f["id"],
                        "attributes": attributes,
                        "relationships": {"build": {"data": {"type": "builds", "id": f["build"]}}},
                    }
                )
            self.page(items, query, path)

        def submission(self, sid: str) -> Json:
            s = state.data["submissions"][sid]
            return {
                "type": "reviewSubmissions",
                "id": sid,
                "attributes": {"platform": "IOS", "state": s["state"]},
                "relationships": {
                    "appStoreVersionForReview": {
                        "data": {"type": "appStoreVersions", "id": s["version"]}
                        if s["version"]
                        else None
                    }
                },
            }

        def submissions(
            self, method: str, parts: list[str], query: dict[str, str], path: str
        ) -> None:
            data = state.data
            if method == "GET" and len(parts) == 1:
                if "filter[app]" not in query:
                    self.error(400, "PARAMETER_ERROR.REQUIRED")
                    return
                states = set(query.get("filter[state]", "").split(",")) - {""}
                items = [
                    self.submission(s)
                    for s, v in data["submissions"].items()
                    if query["filter[app]"] == APP and (not states or v["state"] in states)
                ]
                self.page(items, query, path)
            elif method == "POST" and len(parts) == 1:
                rel = ((self.body() or {}).get("data") or {}).get("relationships") or {}
                if ((rel.get("app") or {}).get("data") or {}).get("id") != APP:
                    self.error(404, "NOT_FOUND")
                    return
                if any(s["state"] == "READY_FOR_REVIEW" for s in data["submissions"].values()):
                    self.error(409, "STATE_ERROR")
                    return
                sid = f"rs-{len(data['submissions']) + 1}"
                data["submissions"][sid] = {"state": "READY_FOR_REVIEW", "version": None}
                self.answer(201, {"data": self.submission(sid)})
            elif method == "PATCH" and len(parts) == 2:
                submission = data["submissions"].get(parts[1])
                if submission is None:
                    self.error(404, "NOT_FOUND")
                    return
                attributes = ((self.body() or {}).get("data") or {}).get("attributes") or {}
                if attributes.get("submitted") is True:
                    if submission["state"] != "READY_FOR_REVIEW" or not submission["version"]:
                        self.error(409, "STATE_ERROR")
                        return
                    submission["state"] = "WAITING_FOR_REVIEW"
                    version = submission["version"]
                    # The review's verdict, where a test set one: it lands as the reviewers
                    # would conclude, after the submission.
                    verdict = data["verdicts"].pop(version, "WAITING_FOR_REVIEW")
                    data["versions"][version]["state"] = verdict
                self.answer(200, {"data": self.submission(parts[1])})
            else:
                self.error(404, "NOT_FOUND")

        # --- Google Play ---------------------------------------------------------------------

        def play(self, method: str, path: str) -> None:
            data = state.data
            if not path.startswith(ROOT + "/edits") and not path == ROOT + "/edits":
                self.answer(404, {"error": {"code": 404, "message": "Package not found"}})
                return
            rest = path[len(ROOT) + len("/edits") :].strip("/")
            if method == "POST" and rest == "":
                edit = str(secrets.randbelow(10**12))
                data["edits"][edit] = copy.deepcopy(data["tracks"])
                self.answer(200, {"id": edit, "expiryTimeSeconds": "1900000000"})
                return
            edit, _, tail = rest.partition("/")
            commit = edit.endswith(":commit")
            edit = edit.removesuffix(":commit")
            tracks = data["edits"].get(edit)
            if tracks is None:
                self.answer(404, {"error": {"code": 404, "message": "Edit not found"}})
                return
            if method == "POST" and commit and not tail:
                data["tracks"] = data["edits"].pop(edit)
                self.answer(200, {"id": edit})
            elif method == "DELETE" and not tail:
                del data["edits"][edit]
                self.answer(200, {})
            elif method == "GET" and tail == "bundles":
                self.answer(
                    200,
                    {
                        "kind": "androidpublisher#bundlesListResponse",
                        "bundles": [
                            {"versionCode": c, "sha1": "0" * 40, "sha256": "0" * 64}
                            for c in data["bundles"]
                        ],
                    },
                )
            elif tail.startswith("tracks/"):
                track = tail.removeprefix("tracks/")
                if track not in tracks:
                    self.answer(404, {"error": {"code": 404, "message": "Track not found"}})
                elif method == "GET":
                    self.answer(200, {"track": track, "releases": tracks[track]})
                elif method == "PUT":
                    given = self.body() or {}
                    releases = given.get("releases") or []
                    codes = {str(c) for c in data["bundles"]}
                    if any(
                        str(c) not in codes for r in releases for c in r.get("versionCodes", [])
                    ):
                        self.answer(400, {"error": {"code": 400, "message": "APK not found"}})
                        return
                    result = _put(tracks[track], releases)
                    if result is None:
                        self.answer(400, {"error": {"code": 400, "message": "Invalid release"}})
                        return
                    tracks[track] = result
                    self.answer(200, {"track": track, "releases": result})
                else:
                    self.answer(405, {"error": {"code": 405}})
            else:
                self.answer(404, {"error": {"code": 404, "message": "Not found"}})

    return Handler


def make_server(host: str, port: int, tokens: set[str]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler(State(tokens)))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9240)
    args = parser.parse_args()
    given = os.environ.get("FAKE_TOKENS", "")
    keys = {given} if given.startswith("{") else set()
    server = make_server(args.host, args.port, keys)
    sys.stderr.write(f"fake app stores at http://{args.host}:{args.port}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
