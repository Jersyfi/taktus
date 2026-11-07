"""Taktus needs no service of its maker to run (UC-10.1, ADR-0284 §8): no licence server, no
account, no telemetry sent home.

What runs is scanned: the control plane's code, the web app's code, and the compose file and
chart an operator installs from. Every address written there names this machine, a service
of the same deployment (a single-label name such as `worker`), a name reserved for examples
(`.test`, `.example`, `.invalid`, `.localhost`), the relay's label, or an identifier that is
never fetched — the namespace of an XML or JSON Schema. The maker's own domain appears once:
as the namespace of the contracts' schemas, an identifier. A new address outside these fails
here, and is either the operator's configuration or a reason to change this test in the open.

What is configured is held by `tests/composition/test_settings.py::
test_an_instance_with_no_setting_reaches_nothing_outside_itself`: with nothing set, no model,
connector, telemetry endpoint or findings intake is named, and the HTTP surface listens on this
machine only.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDRESS = re.compile(r"\bhttps?://([A-Za-z0-9.-]+)")
LOOPBACK = {"127.0.0.1", "localhost", "0.0.0.0"}  # noqa: S104 — a name being checked, not bound
HOST = "host.docker.internal"
"""This machine, as a container of the one-machine installation reaches it: where its local model
server listens by default (ADR-0248)."""
RESERVED = (".test", ".example", ".invalid", ".localhost", ".relay")
"""Names reserved for examples, and `.relay`: the label a client is given whose requests travel
through the database's relay and are never sent over the network (ADR-0156)."""
IDENTIFIERS = {
    "www.omg.org": "the namespaces of BPMN's XML (wire/bpmn.py)",
    "www.w3.org": "the XML Schema instance namespace (wire/bpmn.py)",
    "json-schema.org": "the JSON Schema dialect a schema declares, never fetched",
    "www.googleapis.com": "the OAuth scope a cloud model's token is asked for, never fetched",
}
MAKER = "taktus.eu"
MAKER_USE = ROOT / "src" / "taktus" / "conformance" / "contracts.py"
"""The one file that may name the maker's domain: as the `$id` namespace of the contracts."""
SENDS_HOME = ("posthog", "segment", "mixpanel", "amplitude", "sentry-sdk", "@sentry/", "bugsnag")
"""Libraries whose purpose is to send a product's usage or errors to a service."""


def shipped() -> list[Path]:
    paths = [p for p in (ROOT / "src" / "taktus").rglob("*.py")]
    web = ROOT / "web" / "src"
    paths += [
        p
        for p in web.rglob("*")
        if p.suffix in {".ts", ".svelte", ".js", ".html"}
        and ".test." not in p.name
        and "generated" not in p.parts
    ]
    paths += [ROOT / "deploy" / "docker" / "compose.yml"]
    paths += [p for p in (ROOT / "deploy" / "k8s" / "chart").rglob("*") if p.is_file()]
    return paths


def addresses(path: Path) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if path.suffix in {".ts", ".svelte", ".js"} and line.lstrip().startswith(("//", "*")):
            continue  # a comment pointing a reader at documentation is not called
        found += [
            (match.group(1).lower(), number, line.strip()) for match in ADDRESS.finditer(line)
        ]
    return found


def allowed(host: str, path: Path) -> bool:
    if host in LOOPBACK or host == HOST or "." not in host or host.endswith(RESERVED):
        return True
    if host in IDENTIFIERS:
        return True
    return host == MAKER and path == MAKER_USE


def test_nothing_that_runs_names_a_host_outside_the_deployment() -> None:
    outside = [
        f"{path.relative_to(ROOT)}:{number}: {host} — {line}"
        for path in shipped()
        for host, number, line in addresses(path)
        if not allowed(host, path)
    ]
    assert not outside, "an address outside the deployment:\n" + "\n".join(outside)


def test_the_maker_s_domain_is_only_the_contracts_namespace() -> None:
    uses = [
        (path, number, line)
        for path in shipped()
        for host, number, line in addresses(path)
        if host == MAKER
    ]
    assert uses, "the contracts' namespace names the maker's domain; the scan must see it"
    assert {path for path, _, _ in uses} == {MAKER_USE}
    assert all("NAMESPACE" in line for _, _, line in uses), uses


def test_no_library_whose_purpose_is_to_send_usage_home_is_a_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    declared = [
        *project["project"]["dependencies"],
        *package.get("dependencies", {}),
        *package.get("devDependencies", {}),
    ]
    found = [d for d in declared if any(name in d.lower() for name in SENDS_HOME)]
    assert not found, found
