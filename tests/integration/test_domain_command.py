"""`taktusctl domain` and the incident of a person's stop on the command line (ADR-0280, UC-15.5,
UC-7.2): a domain instantiated with its owner, its duties addressed to that owner, its
conformity evidence generated; a stop of the tenant followed by an incident whose situation
package a person prints."""

from __future__ import annotations

import json
from pathlib import Path

from .test_units_command import ctl


def test_an_owner_reads_the_duties_of_a_domain_and_its_conformity_evidence(tmp_path: Path) -> None:
    state = tmp_path / "state"
    assert ctl(state, "identity", "add", "idn_ada").returncode == 0
    created = ctl(
        state,
        "domain",
        "create",
        "payroll",
        "--name",
        "Payroll",
        "--owner",
        "idn_ada",
        "--jurisdiction",
        "DE",
        "--process",
        "pay-run",
    )
    assert created.returncode == 0, created.stderr
    refused = ctl(
        state, "domain", "create", "hr", "--name", "HR", "--owner", "idn_nobody",
        "--jurisdiction", "DE",
    )  # fmt: skip
    assert refused.returncode == 2 and "no identity" in refused.stderr

    (duties,) = json.loads(ctl(state, "domain", "duties", "--owner", "idn_ada").stdout)
    assert duties["to"] == "idn_ada"
    assert [d["kind"] for d in duties["duties"]] == ["takeover"]
    assert json.loads(ctl(state, "domain", "duties", "--owner", "idn_bo").stdout) == []

    evidence = ctl(state, "domain", "evidence", "--identity", "idn_admin")
    assert evidence.returncode == 0, evidence.stderr
    (payroll,) = json.loads(evidence.stdout)["domains"]
    assert payroll["owner"] == "idn_ada" and payroll["legal_anchors"], "the catalogue in force"


def test_a_person_s_stop_is_followed_by_an_incident_and_its_situation_package(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    stopped = ctl(state, "stop", "tenant", "--identity", "idn_ada")
    assert stopped.returncode == 0, stopped.stderr
    assert json.loads(stopped.stdout)["state"] == "confirmed"
    incidents = json.loads(ctl(state, "incident", "list").stdout)
    (held,) = [i for i in incidents if i["kind"] == "stop.held"]
    assert held["facts"]["role"] == "operator"
    package = ctl(state, "incident", "package", held["id"])
    assert package.returncode == 0, package.stderr
    assert "## What happened" in package.stdout and "found no run to halt" in package.stdout
    assert "idn_ada" not in package.stdout, "the package names no person"
