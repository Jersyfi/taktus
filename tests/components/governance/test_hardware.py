"""Whether a model has what it needs on this machine (ADR-0284 §5, UC-10.1): each declared need
against the inventory — met, missing, or unknown where the machine's figure could not be read.
Only a model on own hardware is checked; one elsewhere needs nothing of this machine."""

from __future__ import annotations

from datetime import UTC, datetime

from taktus.components.governance.application.service import (
    ConfiguredModel,
    ReportHardwareHandler,
)
from taktus.components.governance.domain.model import Fit, NeedStatus
from taktus.components.governance.domain.service.hardware import fit
from taktus.ports.hardware import Accelerator, HardwareInventory, HardwareNeeds, Processors

GIB = 1024**3
AT = datetime(2026, 11, 7, 12, tzinfo=UTC)


def inventory(
    *accelerators: Accelerator, memory: int | None = 64 * GIB, unobserved: str | None = None
) -> HardwareInventory:
    return HardwareInventory(
        at=AT,
        system="Linux 6.8.0",
        processors=Processors(count=16, architecture="x86_64", source="os.cpu_count"),
        memory_bytes=memory,
        memory_source="/proc/meminfo MemTotal" if memory else "nothing answers",
        accelerators=accelerators,
        accelerators_unobserved=unobserved,
    )


CARD = Accelerator(kind="graphics", found_at="/sys/class/drm/card0", memory_bytes=24 * GIB)
NPU = Accelerator(kind="accelerator", found_at="/sys/class/accel/accel0")


def test_a_local_model_that_has_everything_it_needs_fits() -> None:
    needs = HardwareNeeds(
        processors=8,
        memory_bytes=32 * GIB,
        accelerator="graphics",
        accelerator_memory_bytes=16 * GIB,
    )
    seen = fit("model.local", "own", needs, inventory(CARD))
    assert seen.fit is Fit.FITS
    assert [c.status for c in seen.checks] == [NeedStatus.MET] * 3


def test_a_card_with_too_little_memory_leaves_the_model_short_and_says_by_how_much() -> None:
    needs = HardwareNeeds(accelerator="graphics", accelerator_memory_bytes=48 * GIB)
    seen = fit("model.local", "own", needs, inventory(CARD))
    assert seen.fit is Fit.SHORT
    (check,) = seen.checks
    assert check.status is NeedStatus.MISSING
    assert "48.0 GiB" in check.wanted and "24.0 GiB" in check.found


def test_moving_from_a_graphics_card_to_an_accelerator_is_a_change_of_declaration_only() -> None:
    """The same model on a machine with an accelerator instead of a card: the declaration
    `accelerator=graphics` is short there; `accelerator=any` fits both. Nothing but
    configuration changes."""
    on_card = HardwareNeeds(accelerator="graphics")
    assert fit("model.local", "own", on_card, inventory(NPU)).fit is Fit.SHORT
    either = HardwareNeeds(accelerator="any")
    assert fit("model.local", "own", either, inventory(CARD)).fit is Fit.FITS
    assert fit("model.local", "own", either, inventory(NPU)).fit is Fit.FITS


def test_a_figure_the_machine_could_not_give_is_unknown_never_missing() -> None:
    needs = HardwareNeeds(memory_bytes=8 * GIB, accelerator="any")
    seen = fit("model.local", "own", needs, inventory(memory=None, unobserved="no /sys here"))
    assert seen.fit is Fit.UNKNOWN
    assert {c.status for c in seen.checks} == {NeedStatus.UNKNOWN}
    assert "no /sys here" in seen.text


def test_an_accelerator_whose_memory_is_not_stated_is_unknown_for_a_memory_need() -> None:
    needs = HardwareNeeds(accelerator="accelerator", accelerator_memory_bytes=8 * GIB)
    assert fit("model.local", "own", needs, inventory(NPU)).fit is Fit.UNKNOWN


def test_a_model_elsewhere_needs_nothing_here_and_one_undeclared_is_said_to_be() -> None:
    needs = HardwareNeeds(accelerator="graphics")
    assert fit("model.remote", "eu", needs, inventory()).fit is Fit.ELSEWHERE
    undeclared = fit("model.local", "own", HardwareNeeds(), inventory(CARD))
    assert undeclared.fit is Fit.UNDECLARED
    assert "TAKTUS_MODEL_NEEDS" in undeclared.text


class Machine:
    adapter = "platform.hardware"

    async def inventory(self) -> HardwareInventory:
        return inventory(CARD)


async def test_the_report_names_the_machine_and_every_model_and_is_short_when_one_is() -> None:
    report = await ReportHardwareHandler(
        Machine(),
        (
            ConfiguredModel("model.small", "own", HardwareNeeds(memory_bytes=8 * GIB)),
            ConfiguredModel("model.large", "own", HardwareNeeds(memory_bytes=128 * GIB)),
            ConfiguredModel("model.remote", "elsewhere", HardwareNeeds()),
        ),
    ).execute()
    assert report.adapter == "platform.hardware"
    assert [m.fit for m in report.models] == [Fit.FITS, Fit.SHORT, Fit.ELSEWHERE]
    assert report.short
