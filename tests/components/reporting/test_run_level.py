"""The run level of UC-6.10, drawn from a run's facts (ADR-0063, issue #105).

Every element hands over the vocabulary's glyph with motion and without, and both pass the
vocabulary's check; an idle run draws no motion; every element's text carries its method, class,
state, wait and figures; the accounts a wait can name are the run component's.
"""

from __future__ import annotations

from datetime import UTC, datetime

from taktus.components.reporting.application.query import LevelQueries
from taktus.components.reporting.domain.model import Figure, Reader, RunFacts, StepFacts, Wait
from taktus.components.reporting.domain.model.vocabulary import Motion
from taktus.components.reporting.domain.service.drawing import check
from taktus.components.reporting.domain.service.levels import (
    ACCOUNTS,
    drawn_glyphs,
    figures,
    run_level,
)
from taktus.components.run.domain.model import ACCOUNTS as RUN_ACCOUNTS
from taktus.shared.v1 import ConsumptionQuantities, ExactnessClass, Method

AT = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


def facts(*steps: StepFacts, state: str = "running") -> RunFacts:
    return RunFacts(
        id="run_1",
        tenant="default",
        process_version="p@1",
        state=state,
        consumed=ConsumptionQuantities(tokens_in=120, tokens_out=30, currency={"eur": 0.25}),
        steps=steps,
        created_at=AT,
        updated_at=AT,
    )


def step(
    name: str, method: Method, state: str, exactness: ExactnessClass | None = None, **more: object
) -> StepFacts:
    return StepFacts.model_validate(
        {"id": name, "method": method, "exactness": exactness, "state": state, **more}
    )


MIXED = facts(
    step("load", Method.RULE, "succeeded", ExactnessClass.EXACT),
    step(
        "draft",
        Method.LLM,
        "running",
        ExactnessClass.FREE,
        depends_on=("load",),
        consumption=ConsumptionQuantities(tokens_in=120, tokens_out=30),
    ),
    step(
        "approve",
        Method.HUMAN,
        "waiting_human",
        depends_on=("draft",),
        wait=Wait(
            account="wait.human",
            cause="awaiting_decision",
            since=AT,
            role="finance.lead",
            requests=("dr_1",),
        ),
    ),
    step("pause", Method.WAIT, "planned", depends_on=("approve",)),
)


def test_every_element_hands_over_the_vocabularys_glyph_with_motion_and_without() -> None:
    level = run_level(MIXED)
    assert check(drawn_glyphs(level, motion=True), motion=True) == ()
    assert check(drawn_glyphs(level, motion=False), motion=False) == ()


def test_only_the_running_step_moves_and_without_motion_it_has_its_still_mark() -> None:
    level = run_level(MIXED)
    moving = {s.id: s.drawn.moving.motion for s in level.steps}
    assert moving == {
        "load": Motion.NONE,
        "draft": Motion.SHIMMER,
        "approve": Motion.NONE,
        "pause": Motion.NONE,
    }
    draft = next(s for s in level.steps if s.id == "draft")
    assert draft.drawn.still.motion is Motion.NONE
    assert draft.drawn.still.still_mark == "ring_dotted"
    # Nothing but the motion and its still mark differs between the two.
    for s in level.steps:
        assert s.drawn.moving.model_copy(
            update={"motion": Motion.NONE, "still_mark": s.drawn.still.still_mark}
        ) == (s.drawn.still)
    assert level.run.drawn.moving.motion is Motion.NONE


def test_an_idle_run_draws_no_motion() -> None:
    idle = facts(
        step("load", Method.RULE, "succeeded", ExactnessClass.EXACT),
        step("draft", Method.LLM, "succeeded", ExactnessClass.FREE),
        state="finished",
    )
    level = run_level(idle)
    assert all(s.drawn.moving.motion is Motion.NONE for s in level.steps)


def test_the_text_equivalent_carries_the_states_the_wait_and_the_figures() -> None:
    level = run_level(MIXED)
    texts = {s.id: s.text for s in level.steps}
    assert "language model, variable" in texts["draft"] and "running" in texts["draft"]
    assert "tokens_in 120" in texts["draft"] and "tokens_out 30" in texts["draft"]
    assert "waits on a person" in texts["approve"]
    assert "finance.lead" in texts["approve"] and "dr_1" in texts["approve"]
    assert "exact" in texts["load"]
    assert "currency.eur 0.25" in level.run.text and "p@1" in level.run.text


def test_a_figure_is_the_records_quantity_flattened_never_computed_again() -> None:
    quantities = ConsumptionQuantities.model_validate(
        {
            "tokens_in": 10,
            "tokens_by_model": {"m@1": {"input": 7, "cache_read": 3}},
            "currency": {"eur": 0.5, "usd": 0.6},
            "compute_seconds": 2.5,
            "resource_class": "cpu.small",
        }
    )
    assert figures(quantities) == (
        Figure(name="tokens_in", value=10),
        Figure(name="tokens_by_model.m@1.input", value=7),
        Figure(name="tokens_by_model.m@1.cache_read", value=3),
        Figure(name="currency.eur", value=0.5),
        Figure(name="currency.usd", value=0.6),
        Figure(name="compute_seconds.cpu.small", value=2.5),
    )
    assert figures(None) == ()


async def test_a_run_the_predicate_withholds_is_absent_whoever_hands_it_over() -> None:
    class Leaky:
        """Records that hand over a run of another tenant: the predicate still withholds it."""

        async def run(self, tenant: str, run_id: str) -> RunFacts | None:
            return MIXED.model_copy(update={"tenant": "other"})

    reader = Reader(tenant="default", identity="idn_ada")
    assert await LevelQueries(Leaky()).run(reader, "run_1") is None
    seen = await LevelQueries(Leaky()).run(reader.model_copy(update={"tenant": "other"}), "run_1")
    assert seen is not None and seen.run.id == "run_1"


def test_every_account_a_wait_can_name_has_its_words() -> None:
    assert set(ACCOUNTS) == set(RUN_ACCOUNTS)


def test_a_wait_names_no_person() -> None:
    assert set(Wait.model_fields) == {"account", "cause", "since", "on", "role", "requests"}


def test_the_web_apps_fixtures_are_what_make_generate_writes() -> None:
    """The web app's tests draw what `reporting` draws; a stale copy would hold them to an old
    vocabulary (ADR-0063)."""
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("generate", root / "tools" / "generate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate"] = module
    spec.loader.exec_module(module)
    fixtures = root / "web" / "src" / "lib" / "generated" / "fixtures.json"
    assert fixtures.is_file(), "run `make generate`"
    assert fixtures.read_text(encoding="utf-8") == module.web_fixtures(), (
        "web/src/lib/generated/fixtures.json is out of date: run `make generate` and commit it"
    )
