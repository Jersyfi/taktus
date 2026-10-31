# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Whether a change to `contracts/` breaks a published contract (ADR-0171, #396).

Runs as `make gate-compat`, in CI's lane `contracts` (ADR-0096 §6 phase 4). Needs `git` and the
header above, nothing of the project, so that a third party can run it on a checkout.

The **baseline** is the last release: the highest tag `vMAJOR.MINOR.PATCH` with no pre-release
part that is an ancestor of `HEAD`. A release candidate (`v0.2.0-rc.34`) or a beta is not a
release (NTC-0255). Every schema of the baseline (`contracts/<family>/v<N>/<Concept>.json`) is
compared with the schema at the same path now, and every difference is classified from the
consumer's side:

- **breaking** — a document the old schema accepted may now be refused, or something a reader
  could rely on is gone: a removed property, schema or definition, a property newly or no
  longer required, a narrowed type or enum, a new or tighter bound, pattern or format, a changed
  `$id`, `$ref` or condition, and every keyword the classifier does not know;
- **compatible** — what the old schema accepted is still accepted and nothing is gone: an
  added optional property, schema or definition, a widened type or enum, a looser or removed
  bound, a changed description or example.

A contract's `openapi.yaml` is classified by its paths and components: a path, an operation or a
component added is compatible, one removed is breaking, a component schema is compared as above,
and any other change to an operation, a server or the version is breaking.

A breaking change fails. The way to make one is a new major version under a new `$id`
(`contracts/<family>/v2/`, ADR-0019): the baseline's `v1` stays as it was, and a `v1` schema
may be retired only once its successor exists. With no release yet nothing is published and
`v1` may still move (ADR-0019 rule 2); the tool then says so, classifies against `--base` for
the reviewer's information, and passes.

    tools/contract_compat.py                     against the last release; exit 1 on a break
    tools/contract_compat.py --base origin/main  the same; with no release, report against it
    tools/contract_compat.py --baseline REF      against REF, enforced, whatever the tags say

A frozen contract (the freeze record, M3.5) is `make gate-contracts`' to hold: there any change
to a frozen schema fails, compatible or not.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = re.compile(r"contracts/([a-z][a-z0-9-]*)/v([0-9]+)/([A-Za-z0-9]+\.json|openapi\.yaml)")
RELEASE = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")

BREAKING = "breaking"
COMPATIBLE = "compatible"

# Keywords that describe and constrain nothing.
ANNOTATIONS = frozenset(
    {
        "title",
        "description",
        "$comment",
        "examples",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
    }
)
# Keywords that name: any change is breaking.
IDENTITY = frozenset({"$id", "$schema", "$anchor", "$dynamicAnchor", "$ref", "$dynamicRef"})
# A bound a value must reach: raising or adding it narrows.
LOWER = frozenset(
    {"minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties", "minContains"}
)
# A bound a value must stay under: lowering or adding it narrows.
UPPER = frozenset(
    {"maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties", "maxContains"}
)
# A constraint whose change cannot be ordered: adding or changing narrows, removing widens.
CONSTRAINT = frozenset({"pattern", "format", "multipleOf", "contentEncoding", "const"})
# A keyword holding one subschema; absent means `true`, every value accepted.
SUBSCHEMA = frozenset(
    {
        "items",
        "contains",
        "propertyNames",
        "additionalProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
        "then",
        "else",
    }
)
# A keyword holding subschemas by name.
NAMED = frozenset({"properties", "$defs", "definitions"})
# A condition: what it selects changes the meaning of the rest — never ordered.
CONDITION = frozenset({"if", "not"})

Finding = tuple[str, str, str]  # (JSON pointer, kind, what)


@dataclass(frozen=True)
class Change:
    """One classified difference between a baseline schema and the schema now."""

    path: str
    pointer: str
    kind: str
    what: str

    def line(self) -> str:
        where = f"{self.path}#{self.pointer}" if self.pointer else self.path
        return f"{self.kind:<10} {where}: {self.what}"


def _token(name: str) -> str:
    return name.replace("~", "~0").replace("/", "~1")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _types(node: dict[str, Any]) -> set[str] | None:
    value = node.get("type")
    if value is None:
        return None
    return {value} if isinstance(value, str) else set(value)


def _set_change(name: str, old: set[str] | None, new: set[str] | None) -> tuple[str, str]:
    """Classify a change of a set of admitted values; `None` admits every value."""
    if old is None:
        return BREAKING, f"`{name}` added: {sorted(new or ())}"
    if new is None:
        return COMPATIBLE, f"`{name}` removed: every value admitted"
    if new > old:
        return COMPATIBLE, f"`{name}` widened by {sorted(new - old)}"
    if new < old:
        return BREAKING, f"`{name}` narrowed, {sorted(old - new)} no longer admitted"
    return BREAKING, f"`{name}` changed from {sorted(old)} to {sorted(new)}"


def compare(old: Any, new: Any, pointer: str = "") -> Iterator[Finding]:
    """Every difference between two schema nodes, classified."""
    if old == new:
        return
    if isinstance(old, bool) or isinstance(new, bool):
        if old is True or new is False:
            yield pointer, BREAKING, "a schema that admitted more now admits less"
        else:
            yield pointer, COMPATIBLE, "a schema now admits more"
        return
    if not isinstance(old, dict) or not isinstance(new, dict):
        yield pointer, BREAKING, "not a schema on both sides"
        return
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        if before != after:
            yield from _keyword(key, old, new, f"{pointer}/{_token(key)}")


def _keyword(key: str, old: dict[str, Any], new: dict[str, Any], here: str) -> Iterator[Finding]:
    before, after = old.get(key), new.get(key)
    if key in ANNOTATIONS:
        yield here, COMPATIBLE, f"annotation `{key}` changed"
    elif key in IDENTITY:
        yield here, BREAKING, f"`{key}` changed from {before!r} to {after!r}"
    elif key == "type":
        yield (here, *_set_change("type", _types(old), _types(new)))
    elif key == "enum":
        olds = None if before is None else {_canonical(v) for v in before}
        news = None if after is None else {_canonical(v) for v in after}
        yield (here, *_set_change("enum", olds, news))
    elif key == "required":
        for name in sorted(set(after or ()) - set(before or ())):
            yield here, BREAKING, f"property `{name}` newly required"
        for name in sorted(set(before or ()) - set(after or ())):
            yield here, BREAKING, f"property `{name}` no longer required: a reader relied on it"
    elif key == "dependentRequired":
        depended: dict[str, Any] = before or {}
        depending: dict[str, Any] = after or {}
        for name in sorted(set(depended) | set(depending)):
            if depended.get(name) != depending.get(name):
                yield f"{here}/{_token(name)}", BREAKING, "a dependent requirement changed"
    elif key in NAMED:
        yield from _named(key, before or {}, after or {}, here)
    elif key in SUBSCHEMA:
        yield from compare(
            True if before is None else before, True if after is None else after, here
        )
    elif key == "prefixItems":
        yield from _listed("prefixItems", before or [], after or [], here, ordered=True)
    elif key in ("allOf", "anyOf", "oneOf"):
        yield from _combined(key, before, after, here)
    elif key in LOWER or key in UPPER:
        yield _bound(key, before, after, here)
    elif key in CONSTRAINT:
        if after is None:
            yield here, COMPATIBLE, f"`{key}` removed"
        else:
            yield here, BREAKING, f"`{key}` {'added' if before is None else 'changed'}"
    elif key == "uniqueItems":
        if after:
            yield here, BREAKING, "items must now be unique"
        else:
            yield here, COMPATIBLE, "items need no longer be unique"
    elif key in CONDITION:
        yield here, BREAKING, f"condition `{key}` changed: what it selects is not compared"
    else:
        yield here, BREAKING, f"keyword `{key}` is not classified: compare it by hand"


def _named(key: str, before: dict[str, Any], after: dict[str, Any], here: str) -> Iterator[Finding]:
    noun = "property" if key == "properties" else "definition"
    for name in sorted(set(before) | set(after)):
        at = f"{here}/{_token(name)}"
        if name not in after:
            yield at, BREAKING, f"{noun} `{name}` removed"
        elif name not in before:
            yield at, COMPATIBLE, f"{noun} `{name}` added"
        else:
            yield from compare(before[name], after[name], at)


def _listed(
    key: str, before: list[Any], after: list[Any], here: str, ordered: bool = False
) -> Iterator[Finding]:
    """Subschemas of a combination. In `allOf` and `prefixItems` every one constrains, so one
    more narrows; in `anyOf` and `oneOf` every one admits, so one more widens. Where the order
    means nothing, a subschema found unchanged on both sides is matched first, wherever it
    stands; the rest are compared position by position."""
    narrowing = key in ("allOf", "prefixItems")
    olds, news = list(enumerate(before)), list(enumerate(after))
    if not ordered:
        for item in list(olds):
            match = next((other for other in news if other[1] == item[1]), None)
            if match is not None:
                olds.remove(item)
                news.remove(match)
    for index in range(max(len(olds), len(news))):
        if index >= len(news):
            at = f"{here}/{olds[index][0]}"
            yield at, COMPATIBLE if narrowing else BREAKING, f"`{key}` lost a subschema"
        elif index >= len(olds):
            at = f"{here}/{news[index][0]}"
            yield at, BREAKING if narrowing else COMPATIBLE, f"`{key}` gained a subschema"
        else:
            yield from compare(olds[index][1], news[index][1], f"{here}/{news[index][0]}")


def _combined(key: str, before: Any, after: Any, here: str) -> Iterator[Finding]:
    if key != "allOf" and before is None:
        yield here, BREAKING, f"`{key}` added: a value must now match one of its subschemas"
    elif key != "allOf" and after is None:
        yield here, COMPATIBLE, f"`{key}` removed"
    else:
        yield from _listed(key, before or [], after or [], here)


def _bound(key: str, before: Any, after: Any, here: str) -> Finding:
    if after is None:
        return here, COMPATIBLE, f"bound `{key}` removed"
    if before is None:
        return here, BREAKING, f"bound `{key}` added: {after}"
    if (after > before) == (key in LOWER):
        return here, BREAKING, f"bound `{key}` tightened from {before} to {after}"
    return here, COMPATIBLE, f"bound `{key}` loosened from {before} to {after}"


def classify(baseline: dict[str, bytes], current: dict[str, bytes]) -> list[Change]:
    """Every classified change from the baseline's contract files to the current ones.

    Both maps go from a path under the repository (`contracts/worker/v1/Worker.json`) to the
    file's bytes; a path that is not a contract schema is ignored — a README, an example.
    """
    old = {path: data for path, data in baseline.items() if SCHEMA.fullmatch(path)}
    new = {path: data for path, data in current.items() if SCHEMA.fullmatch(path)}
    changes: list[Change] = []
    for path in sorted(set(old) | set(new)):
        if path not in old:
            changes.append(Change(path, "", COMPATIBLE, "schema added"))
        elif path not in new:
            successor = _successor(path, new)
            if successor:
                changes.append(Change(path, "", COMPATIBLE, f"retired; its successor {successor}"))
            else:
                changes.append(Change(path, "", BREAKING, "schema removed, no higher major has it"))
        elif old[path] != new[path]:
            changes.extend(_file(path, old[path], new[path]))
    return changes


def _successor(path: str, current: dict[str, bytes]) -> str | None:
    match = SCHEMA.fullmatch(path)
    if match is None:
        return None
    family, major, name = match.group(1), int(match.group(2)), match.group(3)
    for other in sorted(current):
        found = SCHEMA.fullmatch(other)
        if found and (found.group(1), found.group(3)) == (family, name):
            if int(found.group(2)) > major:
                return other
    return None


def _file(path: str, before: bytes, after: bytes) -> list[Change]:
    try:
        if path.endswith(".json"):
            old, new = json.loads(before), json.loads(after)
        else:
            old, new = yaml.safe_load(before), yaml.safe_load(after)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        return [Change(path, "", BREAKING, f"not readable on one side: {error}")]
    findings = compare(old, new) if path.endswith(".json") else compare_openapi(old, new)
    found = [Change(path, pointer, kind, what) for pointer, kind, what in findings]
    if not found:
        found.append(Change(path, "", COMPATIBLE, "bytes changed, the contract did not"))
    return found


OPENAPI_ANNOTATIONS = frozenset({"info", "tags", "externalDocs", "summary", "description"})
OPERATION_ANNOTATIONS = frozenset({"summary", "description", "tags", "externalDocs"})
METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def compare_openapi(old: Any, new: Any) -> Iterator[Finding]:
    """Every difference between two OpenAPI documents of a contract, classified."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        yield "", BREAKING, "not an OpenAPI document on both sides"
        return
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        here = f"/{_token(key)}"
        if before == after:
            continue
        if key in OPENAPI_ANNOTATIONS:
            yield here, COMPATIBLE, f"annotation `{key}` changed"
        elif key == "paths":
            yield from _paths(before or {}, after or {}, here)
        elif key == "components":
            yield from _components(before or {}, after or {}, here)
        else:
            yield here, BREAKING, f"`{key}` changed"


def _paths(before: dict[str, Any], after: dict[str, Any], here: str) -> Iterator[Finding]:
    for name in sorted(set(before) | set(after)):
        at = f"{here}/{_token(name)}"
        if name not in after:
            yield at, BREAKING, f"path `{name}` removed"
        elif name not in before:
            yield at, COMPATIBLE, f"path `{name}` added"
        elif before[name] != after[name]:
            old, new = before[name], after[name]
            for key in sorted(set(old) | set(new)):
                if old.get(key) == new.get(key):
                    continue
                where = f"{at}/{key}"
                if key in OPERATION_ANNOTATIONS:
                    yield where, COMPATIBLE, f"annotation `{key}` changed"
                elif key in METHODS and key not in new:
                    yield where, BREAKING, f"operation `{key} {name}` removed"
                elif key in METHODS and key not in old:
                    yield where, COMPATIBLE, f"operation `{key} {name}` added"
                elif key in METHODS:
                    yield from _operation(old[key], new[key], where)
                else:
                    yield where, BREAKING, f"`{key}` of path `{name}` changed"


def _operation(old: Any, new: Any, here: str) -> Iterator[Finding]:
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        if key in OPERATION_ANNOTATIONS:
            yield f"{here}/{key}", COMPATIBLE, f"annotation `{key}` changed"
        else:
            yield f"{here}/{key}", BREAKING, f"`{key}` of the operation changed: compare by hand"


def _components(before: dict[str, Any], after: dict[str, Any], here: str) -> Iterator[Finding]:
    for section in sorted(set(before) | set(after)):
        olds, news = before.get(section) or {}, after.get(section) or {}
        for name in sorted(set(olds) | set(news)):
            at = f"{here}/{_token(section)}/{_token(name)}"
            if name not in news:
                yield at, BREAKING, f"component `{section}/{name}` removed"
            elif name not in olds:
                yield at, COMPATIBLE, f"component `{section}/{name}` added"
            elif section == "schemas":
                yield from compare(olds[name], news[name], at)
            elif olds[name] != news[name]:
                yield at, BREAKING, f"component `{section}/{name}` changed: compare by hand"


def last_release(tags: list[str], is_ancestor: Callable[[str], bool]) -> str | None:
    """The highest release tag among `tags` that `is_ancestor` admits. A tag with a
    pre-release part — `-rc.34`, `-beta` — is not a release (NTC-0255)."""
    releases = []
    for tag in tags:
        match = RELEASE.fullmatch(tag)
        if match:
            releases.append((tuple(int(part) for part in match.groups()), tag))
    for _, tag in sorted(releases, reverse=True):
        if is_ancestor(tag):
            return tag
    return None


# --- git and the working tree ----------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    command = ["git", *args]  # git from PATH, arguments from this file and the command line
    return subprocess.run(command, cwd=ROOT, capture_output=True, check=False)  # noqa: S603


def _out(*args: str) -> str:
    done = _git(*args)
    if done.returncode != 0:
        raise SystemExit(f"contract_compat: git {' '.join(args)}: {done.stderr.decode().strip()}")
    return done.stdout.decode()


def files_at(ref: str) -> dict[str, bytes]:
    names = _out("ls-tree", "-r", "--name-only", ref, "--", "contracts").splitlines()
    return {name: _git("show", f"{ref}:{name}").stdout for name in names if SCHEMA.fullmatch(name)}


def files_now() -> dict[str, bytes]:
    found = {}
    for path in sorted((ROOT / "contracts").glob("*/v*/*")):
        name = path.relative_to(ROOT).as_posix()
        if path.is_file() and SCHEMA.fullmatch(name):
            found[name] = path.read_bytes()
    return found


def report(changes: list[Change], against: str) -> None:
    if not changes:
        print(f"contract_compat: no contract schema changed since {against}")
        return
    for change in changes:
        print(f"  {change.line()}")
    broken = sum(change.kind == BREAKING for change in changes)
    print(f"contract_compat: {len(changes)} change(s) since {against}, {broken} breaking")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--baseline", help="compare against this ref, enforced")
    parser.add_argument("--base", help="with no release yet: report against this ref")
    args = parser.parse_args(argv)

    baseline: str | None = args.baseline
    if baseline is None:
        if _out("rev-parse", "--is-shallow-repository").strip() == "true":
            print(
                "contract_compat: a shallow clone has no tags to find the last release in; "
                "fetch the whole history (`fetch-depth: 0`)",
                file=sys.stderr,
            )
            return 2
        baseline = last_release(
            _out("tag", "--list", "v*").split(),
            lambda tag: _git("merge-base", "--is-ancestor", tag, "HEAD").returncode == 0,
        )
    if baseline is None:
        print(
            "contract_compat: no release yet, so no contract is published and v1 may still "
            "move (ADR-0019 rule 2); nothing is enforced"
        )
        if args.base and _git("rev-parse", "--verify", "--quiet", args.base).returncode == 0:
            report(classify(files_at(args.base), files_now()), f"{args.base}, for information")
        return 0
    changes = classify(files_at(baseline), files_now())
    report(changes, baseline)
    if any(change.kind == BREAKING for change in changes):
        print(
            "contract_compat: a published contract changes only compatibly; a breaking change "
            "is a new major version under a new $id (ADR-0019, ADR-0171)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
