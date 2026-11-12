"""The repository's infrastructure as the service reports it: its pipeline runs restarted or
cancelled, its self-hosted runners, its branches, its rate limit and its dependency alerts
(ADR-0201).

Every read is one request per page of 100, bounded by `MAX_PAGES`. The two writes act on one
pipeline run and carry no mark of their own, because the service keeps none on a run. Each is
idempotent by the run's own state instead, weaker than a key and stated so:

- `repository.pipelines.rerun` names the attempt it read. A run whose attempt is already
  higher was rerun since that reading — by this call's earlier attempt, or by somebody else —
  and the repeat reports `replayed` and writes nothing. A run still in progress cannot be
  rerun: the call is a conflict and writes nothing.
- `repository.pipelines.cancel` on a run that is completed already writes nothing and reports
  `replayed`; the service's own 409 for a run it cannot cancel is read the same way once the
  run is read completed.

No answer names a person: a runner is a machine, a branch a name and a commit, and of an
alert the dismisser, the assignees and the requester are never copied (principle 14).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from taktus_connectors.github.api import Api, TargetError, digest_of
from taktus_connectors.github.operations import (
    Outcome,
    _now,
    _read_at,
    _whole,
    invalid,
    read_effect,
    write_effect,
)

type Json = dict[str, Any]

MAX_PAGES = 10
"""Pages of 100 read of a list: a thousand branches, runners or alerts."""
STATES = ("open", "fixed", "dismissed", "auto_dismissed")
SEVERITIES = ("low", "medium", "high", "critical")


def _run_id(input: Json) -> str:
    run = input.get("run")
    if isinstance(run, int) and not isinstance(run, bool):
        run = str(run)
    if not isinstance(run, str) or not run.isdigit():
        raise invalid("run must be the numeric id of a pipeline run")
    return run


def _run(run: Json) -> Json:
    return {
        "id": str(run["id"]),
        "name": str(run.get("name", "")),
        "status": str(run.get("status", "")),
        "conclusion": run.get("conclusion"),
        "attempt": int(run.get("run_attempt") or 1),
        "url": str(run.get("html_url", "")),
    }


def _records(run: Json, kind: str) -> list[Json]:
    return [{"kind": kind, "id": f"{run['id']}#{run['attempt']}", "url": run["url"]}]


async def rerun(api: Api, input: Json, key: str) -> Outcome:
    """Rerun the failed jobs of one completed run, once for the attempt the caller read."""
    run_id = _run_id(input)
    read = input.get("attempt")
    if isinstance(read, bool) or not isinstance(read, int) or read < 1:
        raise invalid("attempt must be the run's attempt as it was read, a whole number from 1")
    found = _run(await api.get(api.repo(f"actions/runs/{run_id}")))
    request: Json = {"run": run_id, "attempt": read}
    digest = digest_of(request)
    if found["attempt"] > read:
        records = _records(found, "pipeline.rerun")
        return Outcome({**found, "rerun": False}, write_effect(records, digest, replayed=True))
    if found["status"] != "completed":
        raise TargetError(
            "conflict", "none", False, "the run is not completed; only a completed run is rerun"
        )
    if found["attempt"] < read:
        raise invalid("the run has no such attempt")
    await api.post(api.repo(f"actions/runs/{run_id}/rerun-failed-jobs"), {})
    after = {**found, "attempt": found["attempt"] + 1, "status": "queued", "conclusion": None}
    return Outcome(
        {**after, "rerun": True},
        write_effect(_records(after, "pipeline.rerun"), digest, replayed=False),
    )


async def cancel(api: Api, input: Json, key: str) -> Outcome:
    """Cancel one run that is queued or in progress; a completed run is left as it is."""
    run_id = _run_id(input)
    digest = digest_of({"run": run_id, "cancel": True})
    found = _run(await api.get(api.repo(f"actions/runs/{run_id}")))
    if found["status"] == "completed":
        records = _records(found, "pipeline.cancel")
        return Outcome({**found, "cancelled": False}, write_effect(records, digest, replayed=True))
    try:
        await api.post(api.repo(f"actions/runs/{run_id}/cancel"), {})
    except TargetError as error:
        if error.cause != "conflict":
            raise
        # The service cannot cancel it: read again whether it completed in the meantime.
        found = _run(await api.get(api.repo(f"actions/runs/{run_id}")))
        if found["status"] != "completed":
            raise
        records = _records(found, "pipeline.cancel")
        return Outcome({**found, "cancelled": False}, write_effect(records, digest, replayed=True))
    return Outcome(
        {**found, "cancelled": True},
        write_effect(_records(found, "pipeline.cancel"), digest, replayed=False),
    )


async def _pages(api: Api, path: str, params: Json, field: str | None) -> tuple[list[Any], bool]:
    """Every item of a paged list, and whether every page was read."""
    page, next_url = await api.get_page(path, {**params, "per_page": 100})
    items: list[Any] = _items(page, field)
    pages = 1
    while next_url and pages < MAX_PAGES:
        page, next_url = await api.get_url(next_url)
        items.extend(_items(page, field))
        pages += 1
    return items, next_url is None


def _items(page: Any, field: str | None) -> list[Any]:
    """The items of one page: the list itself, or the list under `field` of an object."""
    found = page.get(field) if field and isinstance(page, dict) else page
    if not isinstance(found, list):
        raise TargetError("unexpected", "none", False, "a page of the list is not a list")
    return list(found)


async def list_runners(api: Api, input: Json, key: str) -> Outcome:
    """The repository's self-hosted runners: each one's id, name, operating system, whether it
    is online and whether it is busy, and its labels by name."""
    found, complete = await _pages(api, api.repo("actions/runners"), {}, "runners")
    runners = [
        {
            "id": str(r["id"]),
            "name": str(r.get("name", "")),
            "os": r.get("os"),
            "status": str(r.get("status", "")),
            "busy": bool(r.get("busy", False)),
            "labels": sorted(str(label.get("name", "")) for label in r.get("labels") or []),
        }
        for r in found
    ]
    output = {
        "runners": runners,
        "count": len(runners),
        "offline": sum(1 for r in runners if r["status"] != "online"),
        "complete": complete,
    }
    return Outcome(output, read_effect())


async def list_branches(api: Api, input: Json, key: str) -> Outcome:
    """The repository's branches: each one's name, head commit and whether it is protected."""
    params: Json = {}
    protected = input.get("protected")
    if protected is not None:
        if not isinstance(protected, bool):
            raise invalid("protected is true or false")
        params["protected"] = "true" if protected else "false"
    found, complete = await _pages(api, api.repo("branches"), params, None)
    branches = [
        {
            "name": str(b["name"]),
            "head_sha": str((b.get("commit") or {}).get("sha") or "") or None,
            "protected": bool(b.get("protected", False)),
        }
        for b in found
    ]
    output = {"branches": branches, "count": len(branches), "complete": complete}
    return Outcome(output, read_effect())


async def rate_limit(api: Api, input: Json, key: str) -> Outcome:
    """The requesting identity's rate limits, one entry per resource the service names, each
    with its limit, what was used and the share used as decimal text. The service does not
    count this request against any of them."""
    answer = await api.get("/rate_limit")
    resources = answer.get("resources") if isinstance(answer, dict) else None
    if not isinstance(resources, dict):
        raise TargetError("unexpected", "none", False, "the answer names no resources")
    now = _now()
    listed: list[Json] = []
    for name, figure in sorted(resources.items()):
        if not isinstance(figure, dict) or not isinstance(figure.get("limit"), int):
            continue
        limit, used = int(figure["limit"]), int(figure.get("used", 0))
        reset = figure.get("reset")
        listed.append(
            {
                "resource": str(name),
                "limit": limit,
                "used": used,
                "remaining": int(figure.get("remaining", limit - used)),
                # Decimal text to four places: the share an exact rule compares (CLAUDE.md §4).
                "used_share": "0.0000" if limit <= 0 else _share(used, limit),
                "reset_minutes": None
                if not isinstance(reset, int)
                else max(0, (reset - int(now.timestamp())) // 60),
            }
        )
    listed.sort(key=lambda r: (-_tenths_of_mille(r), str(r["resource"])))
    return Outcome({"resources": listed, "read_at": _read_at(now)}, read_effect())


def _tenths_of_mille(resource: Json) -> int:
    return int(resource["used"]) * 10_000 // max(int(resource["limit"]), 1)


def _share(used: int, limit: int) -> str:
    """`used / limit`, rounded down to four decimal places, as text."""
    whole = used * 10_000 // limit
    return f"{whole // 10_000}.{whole % 10_000:04d}"


def _alert(alert: Json, now: Any) -> Json:
    advisory = alert.get("security_advisory") or {}
    vulnerability = alert.get("security_vulnerability") or {}
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or vulnerability.get("package") or {}
    patched = vulnerability.get("first_patched_version") or {}
    return {
        "number": int(alert["number"]),
        "state": str(alert.get("state", "")),
        "severity": str(vulnerability.get("severity") or advisory.get("severity") or ""),
        "ghsa_id": advisory.get("ghsa_id"),
        "cve_id": advisory.get("cve_id"),
        "summary": str(advisory.get("summary") or ""),
        "ecosystem": package.get("ecosystem"),
        "package": package.get("name"),
        "manifest": dependency.get("manifest_path"),
        "scope": dependency.get("scope"),
        "vulnerable": vulnerability.get("vulnerable_version_range"),
        "patched": patched.get("identifier") if isinstance(patched, dict) else None,
        "url": str(alert.get("html_url", "")),
        "created_at": str(alert.get("created_at", "")),
        "age_days": _whole(alert.get("created_at"), now, 86_400),
    }


def _choices(input: Json, name: str, allowed: tuple[str, ...], default: str | None) -> str | None:
    value = input.get(name, default)
    if value is None:
        return None
    values = value if isinstance(value, list) else [value]
    if not values or any(v not in allowed for v in values):
        raise invalid(f"{name} is one or a list of {', '.join(allowed)}")
    return ",".join(str(v) for v in values)


async def list_alerts(api: Api, input: Json, key: str) -> Outcome:
    """The repository's dependency alerts in `state` (default `open`), optionally of
    `severity`, newest first: each with its advisory's identifiers and summary, the package,
    the vulnerable range and the first patched version where one exists."""
    params: Json = {"state": _choices(input, "state", STATES, "open")}
    severity = _choices(input, "severity", SEVERITIES, None)
    if severity:
        params["severity"] = severity
    found, complete = await _pages(api, api.repo("dependabot/alerts"), params, None)
    now = _now()
    alerts = [_alert(a, now) for a in found]
    output = {
        "alerts": alerts,
        "count": len(alerts),
        "complete": complete,
        "read_at": _read_at(now),
    }
    return Outcome(output, read_effect())


type Operation = Callable[[Api, Json, str], Awaitable[Outcome]]

OPERATIONS: dict[str, Operation] = {
    "repository.pipelines.rerun": rerun,
    "repository.pipelines.cancel": cancel,
    "repository.runners.list": list_runners,
    "repository.branches.list": list_branches,
    "repository.ratelimit.read": rate_limit,
    "repository.advisories.list": list_alerts,
}
