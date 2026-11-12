"""A model may explain the exactness statement to a reader, and the explanation names the
statement it explains (UC-6.9 §2, ADR-0023 §4, ADR-0226, #224).

An `llm` step whose prompt reads `{"$run": "exactness"}` receives the statement as the process
component renders it. What leaves the step is the model's text and a closing line the run
writes — never the model — naming the version and the digest of the statement it explained.
The statement itself is never written by a model, and the explanation never replaces it."""

from __future__ import annotations

import hashlib
import json

from components.run.test_engine import rule
from components.run.test_llm_steps import ModelHarness
from fakes import FakeModel

from taktus.components.run.domain.model import RunState
from taktus.shared.v1 import ExactnessClass, Fallback, Method, Step

STATEMENT = "# Exactness statement — p (p@1)\n\n## Which checks apply\n\n- `total` (exact): bounds."


class Statements:
    async def rendered(self, tenant: str, process_version: str) -> str | None:
        return STATEMENT if process_version == "p@1" else None


def explain(values: dict[str, object]) -> tuple[Step, dict[str, object]]:
    step = Step(
        id="explain",
        method=Method.LLM,
        reason="a reader asks in their own words",
        rejected=(),
        exactness=ExactnessClass.FREE,
        fallback=Fallback(when="the model is unavailable", to=Method.HUMAN),
        depends_on=("total",),
    )
    return step, {
        "purpose": "reasoning",
        "prompt": "Explain this to a reader:\n${statement}",
        "values": values,
    }


async def _answer(h: ModelHarness) -> dict[str, object]:
    run = await h.start()
    assert run.state is RunState.FINISHED, run
    checkpoint = run.step_run("explain").checkpoint
    assert checkpoint is not None and checkpoint.result_digest is not None
    content = await h.objects.get(checkpoint.result_digest)
    assert content is not None
    answer = json.loads(content)
    assert isinstance(answer, dict)
    return answer


async def test_a_model_s_explanation_names_the_statement_it_explains() -> None:
    h = ModelHarness(
        rule("total", {"rule": "constant", "value": 42}),
        explain({"statement": {"$run": "exactness"}}),
        model=FakeModel(answer="Each total is checked against bounds."),
    )
    h.engine._statements = Statements()
    answer = await _answer(h)
    digest = hashlib.sha256(STATEMENT.encode("utf-8")).hexdigest()
    assert answer["explains"] == {"statement": "p@1", "digest": f"sha256:{digest}"}
    text = str(answer["text"])
    assert text.startswith("Each total is checked against bounds.")
    assert text.endswith("generated from the process version, is what holds.")
    assert f"p@1 (sha256:{digest[:16]})" in text
    assert STATEMENT in h.model.prompts[0].user, "the model read the statement unchanged"


async def test_a_model_s_answer_that_read_no_statement_names_none() -> None:
    h = ModelHarness(
        rule("total", {"rule": "constant", "value": 42}),
        explain({"statement": {"$from": "total"}}),
        model=FakeModel(answer="42."),
    )
    h.engine._statements = Statements()
    answer = await _answer(h)
    assert "explains" not in answer and answer["text"] == "42."
