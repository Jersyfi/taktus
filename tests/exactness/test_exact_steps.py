"""ADR-0014, ADR-0018: an `exact` step never takes its final value from a variable method.

Held on three levels. The model: the shared kernel's `Step` and the process domain refuse an
exact step on any method but rule or statistics, and a process version containing one does not
exist. The bundles: every example bundle under examples/processes loads, and no step in any of
them is classed exact on a method outside the admissible set. Execution: the run component has
no road by which a worker's output becomes an exact step's result — the value comes from a rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.model import InvalidProcess, ProcessVersion
from taktus.components.process.domain.service import validation
from taktus.components.run.domain.model import parse_work
from taktus.shared.v1 import (
    EXACT_ADMISSIBLE,
    PRODUCING,
    VARIABLE,
    ExactnessClass,
    Fallback,
    Method,
    Step,
)

ROOT = Path(__file__).resolve().parents[2]
BUNDLES = sorted((ROOT / "examples" / "processes").glob("*.yaml")) + sorted(
    (ROOT / "blueprints").glob("*/processes/*.yaml")
)
SHARED_EXAMPLES = ROOT / "contracts" / "shared" / "v1" / "examples" / "step"


def exact_step(method: Method) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "s",
        "method": method,
        "reason": "r",
        "rejected": [],
        "exactness": ExactnessClass.EXACT,
    }
    if method in VARIABLE:
        fields["fallback"] = Fallback(when="always", to=Method.HUMAN)
    if method in (Method.ML, Method.NEURAL):
        fields["model"] = "m@1"
    return fields


@pytest.mark.parametrize("method", sorted(PRODUCING))
def test_only_rule_and_statistics_may_produce_an_exact_result(method: Method) -> None:
    if method in EXACT_ADMISSIBLE:
        assert Step.model_validate(exact_step(method)).exactness is ExactnessClass.EXACT
    else:
        with pytest.raises(ValidationError, match="exact result comes from rule, statistics only"):
            Step.model_validate(exact_step(method))


@pytest.mark.parametrize("method", sorted(PRODUCING - EXACT_ADMISSIBLE))
def test_the_process_domain_refuses_it_on_its_own(method: Method) -> None:
    unvalidated = Step.model_construct(**exact_step(method))
    assert any("classed exact" in f for f in validation.exactness_admits_method(unvalidated))
    with pytest.raises(InvalidProcess, match="classed exact"):
        ProcessVersion.model_construct(
            process_id="p", version="1", name="P", autonomy_level=2, steps=(unvalidated,)
        )._valid_graph()


@pytest.mark.parametrize("method", sorted(VARIABLE))
def test_a_process_with_an_exact_step_on_a_variable_method_does_not_exist(method: Method) -> None:
    bundle = {
        "id": "p",
        "version": "1",
        "name": "P",
        "steps": [{**exact_step(method), "fallback": {"when": "always", "to": "human"}, "id": "s"}],
    }
    with pytest.raises(InvalidProcess) as raised:
        parse_bundle(bundle)
    assert any("exact" in f for f in raised.value.findings)


def test_the_kernel_examples_agree() -> None:
    import json

    rejected = json.loads((SHARED_EXAMPLES / "invalid" / "exact-step-on-llm.json").read_text())
    with pytest.raises(ValidationError):
        Step.model_validate(rejected)
    accepted = json.loads((SHARED_EXAMPLES / "valid" / "book-amount.json").read_text())
    assert Step.model_validate(accepted).method is Method.RULE


@pytest.mark.parametrize("bundle_path", BUNDLES, ids=lambda p: p.name)
def test_every_example_bundle_keeps_exact_results_with_admissible_methods(
    bundle_path: Path,
) -> None:
    with bundle_path.open(encoding="utf-8") as handle:
        version = parse_bundle(yaml.safe_load(handle))
    exact = [s for s in version.steps if s.exactness is ExactnessClass.EXACT]
    assert exact, f"{bundle_path.name} exercises no exact step"
    for step in exact:
        assert step.method in EXACT_ADMISSIBLE, f"{bundle_path.name}: {step.id} on {step.method}"


@pytest.mark.parametrize("bundle_path", BUNDLES, ids=lambda p: p.name)
def test_an_exact_step_s_value_comes_from_a_rule_at_run_time(bundle_path: Path) -> None:
    """What executes an exact step is a rule of the run component, never a worker: its work
    parses as rule work, and a rule that reads a worker's artifact is the check pattern."""
    with bundle_path.open(encoding="utf-8") as handle:
        version = parse_bundle(yaml.safe_load(handle))
    for step in version.steps:
        if step.exactness is not ExactnessClass.EXACT:
            continue
        examples = {name: declared.example for name, declared in version.inputs.items()}
        work = parse_work(step, version.work.get(step.id), examples)
        assert type(work).__name__.endswith("Rule"), f"{step.id} would not run as a rule"
        assert not step.required_capabilities, f"{step.id} would need an adapter"
