"""How the secrets' metadata is asked and read: `secrets.metadata.list` over Secrets Manager.

The API answers `POST /` with `X-Amz-Target: secretsmanager.ListSecrets`, signed for the
service `secretsmanager` in the configured region. `ListSecrets` answers metadata only: its
entries hold no secret value. The connector never calls `GetSecretValue` or
`BatchGetSecretValue`, the two actions that answer a value, nor any other action.

A `prefix` is sent as the documented filter of the key `name`, a case-sensitive prefix match.
A prefix that begins with `!` is refused: the provider reads a leading `!` as a negation.
Pages are read with `MaxResults` and `NextToken`. The provider documents that a `NextToken`
may come with an empty page, so the connector follows it, up to `MAX_PAGES` requests.

Each secret's fields:

- `changed_at` is `LastRotatedDate` where the secret was ever rotated, otherwise
  `LastChangedDate` (the last change of any kind), otherwise `CreatedDate`.
- `rotation.automatic` is `RotationEnabled`; `rotation.period_days` is
  `RotationRules.AutomaticallyAfterDays` (null where the rule is a schedule expression);
  `rotation.next_at` is `NextRotationDate`.
- `expires_at` is always null: the store sets no expiry on a secret.
- `last_accessed_at` is `LastAccessedDate`, which the provider gives to the day.

The provider gives every moment as seconds since the epoch; each becomes RFC 3339 in UTC.
The description, the tags and the ARN are not copied.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from taktus_connectors.aws.api import Config, from_epoch, key_of, post, rfc3339
from taktus_connectors.serving import Call, Outcome, TargetError, invalid

type Json = dict[str, Any]

SERVICE = "secretsmanager"
ACTION = "secretsmanager.ListSecrets"
LIMIT = 100
MAX_LIMIT = 500
PAGE = 100
"""The most entries the provider answers in one page (`MaxResults`)."""
MAX_PAGES = 20
"""How many requests one read makes at most; empty pages count."""
MAX_PREFIX = 512


def _limit(input: Json) -> int:
    value = input.get("limit", LIMIT)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMIT:
        raise invalid(f"limit must be a whole number from 1 to {MAX_LIMIT}")
    return value


def _prefix(input: Json) -> str | None:
    value = input.get("prefix")
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > MAX_PREFIX:
        raise invalid(f"prefix must be a text of at most {MAX_PREFIX} characters")
    if value.startswith("!"):
        raise invalid("prefix must not begin with `!`, which the store reads as a negation")
    return value


def _moment(entry: Json, name: str) -> datetime | None:
    return from_epoch(entry.get(name), 1)


def _stamp(moment: datetime | None) -> str | None:
    return rfc3339(moment) if moment is not None else None


def secret(entry: Any, at: datetime) -> Json:
    """The metadata a process judges a secret by; never its value."""
    if not isinstance(entry, dict) or not isinstance(entry.get("Name"), str):
        raise TargetError("unexpected", "none", False, "a secret has no name")
    changed = (
        _moment(entry, "LastRotatedDate")
        or _moment(entry, "LastChangedDate")
        or _moment(entry, "CreatedDate")
    )
    rules = entry.get("RotationRules")
    period = rules.get("AutomaticallyAfterDays") if isinstance(rules, dict) else None
    enabled = entry.get("RotationEnabled")
    return {
        "name": entry["Name"],
        "created_at": _stamp(_moment(entry, "CreatedDate")),
        "changed_at": _stamp(changed),
        "age_days": (at - changed) // timedelta(days=1) if changed is not None else None,
        "rotation": {
            "automatic": enabled if isinstance(enabled, bool) else None,
            "period_days": period
            if isinstance(period, int) and not isinstance(period, bool)
            else None,
            "next_at": _stamp(_moment(entry, "NextRotationDate")),
        },
        "expires_at": None,
        "last_accessed_at": _stamp(_moment(entry, "LastAccessedDate")),
    }


async def list_(config: Config, call: Call, input: Json) -> Outcome:
    limit = _limit(input)
    prefix = _prefix(input)
    key = key_of(call)
    body: Json = {}
    if prefix is not None:
        body["Filters"] = [{"Key": "name", "Values": [prefix]}]
    read_at = datetime.now(UTC)
    found: list[Json] = []
    token: Any = None
    for _ in range(MAX_PAGES):
        asked = {**body, "MaxResults": min(PAGE, limit - len(found))}
        if token:
            asked["NextToken"] = token
        answer = await post(
            config,
            call,
            key,
            address=config.secrets(),
            region=config.services_region,
            service=SERVICE,
            action=ACTION,
            body=asked,
            what="the secrets' metadata",
        )
        page = answer.get("SecretList", [])
        if not isinstance(page, list):
            raise TargetError("unexpected", "none", False, "the answer's SecretList is not a list")
        found.extend(secret(entry, read_at) for entry in page)
        token = answer.get("NextToken")
        if not token or len(found) >= limit:
            break
    complete = not token and len(found) <= limit
    ordered = sorted(
        found[:limit],
        key=lambda s: (s["age_days"] is None, -(s["age_days"] or 0), s["name"]),
    )
    output: Json = {"secrets": ordered, "complete": complete, "read_at": rfc3339(read_at)}
    return Outcome(output=output, effect={"kind": "read"})
