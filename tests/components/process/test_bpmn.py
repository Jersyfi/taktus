"""BPMN in as a plan draft, out as a projection of a version (UC-4.23, ADR-0168).

The model below is the kind an organisation keeps: lanes named after departments, a user task, a
service task, an exclusive gateway whose conditions are words, a parallel split and join, a loop
back for a correction, a performer assignment and a timer start. It is read into a draft that
chooses no method, and a draft becomes a bundle only once the person filled it in. Every bundle
of the repository is exported and read back with its graph, its roles and its gateways.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from taktus.adapters.driving.cli.bpmn_command import bpmn as bpmn_cli
from taktus.components.process.application.service import drafts
from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.service import interchange
from taktus.shared.v1 import Method
from taktus.wire import bpmn

ROOT = Path(__file__).resolve().parents[3]
BUNDLES = sorted(
    p
    for p in [*(ROOT / "blueprints").rglob("*.yaml"), *(ROOT / "examples").rglob("*.yaml")]
    if "steps" in (yaml.safe_load(p.read_text(encoding="utf-8")) or {})
)

MODEL = b"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" id="d" targetNamespace="urn:example">
  <bpmn:process id="Process_Invoice" name="Incoming invoice" isExecutable="true">
    <bpmn:laneSet id="ls">
      <bpmn:lane id="Lane_Acc" name="Accounts payable">
        <bpmn:flowNodeRef>Task_Check</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Task_Approve</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="Lane_Sys" name="ERP">
        <bpmn:flowNodeRef>Task_Read</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Task_Book</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Task_Archive</bpmn:flowNodeRef>
      </bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="Start"><bpmn:timerEventDefinition id="t"/></bpmn:startEvent>
    <bpmn:serviceTask id="Task_Read" name="Read invoice"/>
    <bpmn:userTask id="Task_Check" name="Check invoice">
      <bpmn:potentialOwner id="po"><bpmn:resourceAssignmentExpression>
        <bpmn:formalExpression>jane.doe</bpmn:formalExpression>
      </bpmn:resourceAssignmentExpression></bpmn:potentialOwner>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="Gw_Amount" default="F_small"/>
    <bpmn:userTask id="Task_Approve" name="Approve payment"/>
    <bpmn:parallelGateway id="Gw_Fork"/>
    <bpmn:businessRuleTask id="Task_Book" name="Book invoice"/>
    <bpmn:task id="Task_Archive" name="Archive invoice"/>
    <bpmn:parallelGateway id="Gw_Join"/>
    <bpmn:endEvent id="End"/>
    <bpmn:dataObject id="Data_1"/>
    <bpmn:sequenceFlow id="F1" sourceRef="Start" targetRef="Task_Read"/>
    <bpmn:sequenceFlow id="F2" sourceRef="Task_Read" targetRef="Task_Check"/>
    <bpmn:sequenceFlow id="F3" sourceRef="Task_Check" targetRef="Gw_Amount"/>
    <bpmn:sequenceFlow id="F_big" sourceRef="Gw_Amount" targetRef="Task_Approve">
      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">amount over 1000
      </bpmn:conditionExpression>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="F_small" sourceRef="Gw_Amount" targetRef="Gw_Fork"/>
    <bpmn:sequenceFlow id="F_back" sourceRef="Task_Approve" targetRef="Task_Check"/>
    <bpmn:sequenceFlow id="F5" sourceRef="Task_Approve" targetRef="Gw_Fork"/>
    <bpmn:sequenceFlow id="F6" sourceRef="Gw_Fork" targetRef="Task_Book"/>
    <bpmn:sequenceFlow id="F7" sourceRef="Gw_Fork" targetRef="Task_Archive"/>
    <bpmn:sequenceFlow id="F8" sourceRef="Task_Book" targetRef="Gw_Join"/>
    <bpmn:sequenceFlow id="F9" sourceRef="Task_Archive" targetRef="Gw_Join"/>
    <bpmn:sequenceFlow id="F10" sourceRef="Gw_Join" targetRef="End"/>
  </bpmn:process>
</bpmn:definitions>
"""


def the_draft() -> Any:
    (draft,) = drafts.read_drafts(MODEL)
    return draft


def fill(document: dict[str, Any]) -> dict[str, Any]:
    """The person's answers to every question of the model's draft."""
    answers: dict[str, dict[str, Any]] = {
        "read-invoice": {"method": "worker", "exactness": "sourced",
                         "fallback": {"when": "the document cannot be read", "to": "human"}},
        "check-invoice": {"method": "human"},
        "approve-payment": {"method": "human",
                            "when": [{"value": {"$input": "amount"}, "matches": "^[0-9]{4,}"}]},
        "book-invoice": {"method": "rule", "exactness": "exact",
                         "checks": [{"kind": "recomputation", "subject": "the booking"}]},
        "archive-invoice": {"method": "worker", "exactness": "free",
                            "fallback": {"when": "the archive refuses it", "to": "human"}},
    }  # fmt: skip
    for step in document["steps"]:
        step.update(answers[step["id"]])
        step["reason"] = f"what {step['name']} needs"
        step["rejected"] = [{"method": "llm", "why": "it adds nothing here"}]
        if step["id"] == "book-invoice":
            step["work"] = {"rule": "check", "conditions": [{"value": "x", "equals": "x"}]}
    document["confirmed"] = list(document["roles"].values())
    return document


def test_an_import_yields_a_plan_draft_with_its_steps_as_proposals_and_no_method_chosen() -> None:
    draft = the_draft()
    assert draft.kind == "draft"
    assert draft.id == "incoming-invoice"
    assert [s.id for s in draft.steps] == [
        "read-invoice", "check-invoice", "approve-payment", "book-invoice", "archive-invoice"
    ]  # fmt: skip
    assert all(s.method is None for s in draft.steps)
    by = {s.id: s for s in draft.steps}
    assert by["check-invoice"].candidates == (Method.HUMAN,)
    assert by["book-invoice"].candidates == (Method.RULE, Method.STATISTICS, Method.ML)
    assert by["archive-invoice"].candidates == tuple(Method)
    assert by["read-invoice"].depends_on == ()
    assert by["check-invoice"].depends_on == ("read-invoice",)
    assert set(by["book-invoice"].depends_on) == {"check-invoice", "approve-payment"}
    assert by["approve-payment"].condition == "amount over 1000"
    assert by["approve-payment"].when is None
    assert draft.level == 1
    assert {g.kind for g in draft.gateways} == {"exclusive", "parallel"}
    asked = {(q.about, q.asks.split(" ")[0]) for q in draft.questions}
    assert {(s.id, "choose") for s in draft.steps} <= asked
    assert ("approve-payment", "state") in asked
    assert ("accounts-payable", "confirm") in asked


def test_a_lane_suggests_a_role_and_a_performer_is_never_imported() -> None:
    draft = the_draft()
    assert draft.roles == {"Accounts payable": "accounts-payable", "ERP": "erp"}
    assert draft.step("check-invoice").role == "accounts-payable"
    assert "jane" not in yaml.safe_dump(draft.document())
    assert any("performer of 'check-invoice'" in line for line in draft.not_imported)


def test_a_loop_the_model_draws_is_not_imported_and_the_draft_says_where_it_was() -> None:
    draft = the_draft()
    assert "approve-payment" not in draft.step("check-invoice").depends_on
    assert any("closes a loop" in line for line in draft.not_imported)
    assert any("timerEventDefinition" in line for line in draft.not_imported)
    assert not any("dataObject" in line for line in draft.not_imported)


def test_a_draft_is_never_a_version_and_is_refused_with_every_question_named() -> None:
    document = the_draft().document()
    with pytest.raises(InvalidProcess):
        parse_bundle(document)
    with pytest.raises(InvalidProcess) as refused:
        drafts.complete(document)
    named = "\n".join(refused.value.findings)
    for step in document["steps"]:
        assert step["id"] in named
    assert "amount over 1000" in named
    assert "Accounts payable" in named


def test_a_filled_draft_becomes_a_bundle_that_registers() -> None:
    bundle = drafts.complete(fill(the_draft().document()))
    version = parse_bundle(bundle)
    assert version.process_id == "incoming-invoice"
    assert version.autonomy.level == 1
    assert version.step("check-invoice").role == "accounts-payable"
    assert version.step("read-invoice").fallback is not None
    assert version.step("read-invoice").fallback.role == "erp"  # type: ignore[union-attr]
    assert version.work["approve-payment"]["when"][0]["matches"] == "^[0-9]{4,}"


def test_an_unconfirmed_role_does_not_reach_the_bundle() -> None:
    document = fill(the_draft().document())
    document["confirmed"] = ["erp"]
    with pytest.raises(InvalidProcess) as refused:
        drafts.complete(document)
    assert any("Accounts payable" in f for f in refused.value.findings)


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_an_export_round_trips_the_graph_the_roles_and_the_gateways(path: Path) -> None:
    version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
    model = interchange.model_of(version)
    (again,) = bpmn.read(bpmn.write(model))
    assert again == model
    (draft,) = drafts.read_drafts(drafts.export(version))
    assert draft.id == version.process_id
    assert [s.id for s in draft.steps] == [s.id for s in version.steps]
    for step, original in zip(draft.steps, version.steps, strict=True):
        assert set(step.depends_on) == set(original.dependencies), step.id
        assert step.role == original.performer, step.id
        assert step.method is None and step.suggested is original.method, step.id
        when = (version.work.get(step.id) or {}).get("when")
        assert step.when == (tuple(when) if when else None), step.id
    assert draft.gateways == interchange.draft_of(model).gateways
    conditioned = {s for s, w in ((s.id, (version.work.get(s.id) or {}).get("when")) for s in
                   version.steps) if w}  # fmt: skip
    splits = [g for g in draft.gateways if g.kind == "exclusive" and len(g.after) >= 1]
    assert {s for g in splits for s in g.after if s in conditioned} == conditioned


def test_the_bundles_exported_carry_every_gateway_kind_and_a_role() -> None:
    kinds: set[str] = set()
    roles: set[str] = set()
    for path in BUNDLES:
        version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
        (draft,) = drafts.read_drafts(drafts.export(version))
        kinds |= {g.kind for g in draft.gateways}
        roles |= {s.role for s in draft.steps if s.role}
    assert kinds == {"exclusive", "parallel"}
    assert roles


def test_an_export_carries_a_diagram_a_tool_can_show() -> None:
    version = parse_bundle(yaml.safe_load(BUNDLES[0].read_text(encoding="utf-8")))
    written = drafts.export(version).decode()
    for step in version.steps:
        assert f'bpmnElement="{step.id}"' in written
    assert "BPMNDiagram" in written
    assert 'isExecutable="false"' in written


@pytest.mark.parametrize(
    "document",
    [
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
        b'<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">&b;</definitions>',
        b'<?xml version="1.0"?><!DOCTYPE d SYSTEM "file:///etc/passwd">'
        b'<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>',
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "https://example.org/x">]>'
        b'<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">&x;</definitions>',
    ],
    ids=["entity-expansion", "external-document-type", "external-entity"],
)
def test_a_model_with_a_document_type_or_an_entity_is_refused(document: bytes) -> None:
    with pytest.raises(bpmn.Unreadable, match="declares"):
        bpmn.read(document)


def test_a_model_too_large_or_of_another_kind_is_refused() -> None:
    with pytest.raises(bpmn.Unreadable, match="larger"):
        bpmn.read(b" " * (bpmn.MAX_BYTES + 1))
    with pytest.raises(bpmn.Unreadable, match="no BPMN"):
        bpmn.read(b"<definitions/>")
    with pytest.raises(bpmn.Unreadable, match="well-formed"):
        bpmn.read(b"<definitions")
    with pytest.raises(bpmn.Unreadable, match="no process with a task"):
        drafts.read_drafts(b'<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"/>')


def test_the_command_line_drafts_completes_and_exports_without_an_instance(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    model = tmp_path / "invoice.bpmn"
    model.write_bytes(MODEL)
    drafted = runner.invoke(bpmn_cli, ["draft", str(model)])
    assert drafted.exit_code == 0, drafted.output
    draft_file = tmp_path / "draft.yaml"
    draft_file.write_text(drafted.output, encoding="utf-8")
    refused = runner.invoke(bpmn_cli, ["complete", str(draft_file)])
    assert refused.exit_code == 1
    draft_file.write_text(yaml.safe_dump(fill(yaml.safe_load(drafted.output))), encoding="utf-8")
    completed = runner.invoke(bpmn_cli, ["complete", str(draft_file), "--version", "7"])
    assert completed.exit_code == 0, completed.output
    bundle_file = tmp_path / "bundle.yaml"
    bundle_file.write_text(completed.output, encoding="utf-8")
    assert isinstance(parse_bundle(yaml.safe_load(completed.output)), ProcessVersion)
    out = tmp_path / "out.bpmn"
    exported = runner.invoke(bpmn_cli, ["export", str(bundle_file), "--out", str(out)])
    assert exported.exit_code == 0, exported.output
    (again,) = drafts.read_drafts(out.read_bytes())
    assert again.step("check-invoice").role == "accounts-payable"
    unreadable = tmp_path / "bad.bpmn"
    unreadable.write_bytes(b"<!DOCTYPE x><x/>")
    assert runner.invoke(bpmn_cli, ["draft", str(unreadable)]).exit_code == 2
