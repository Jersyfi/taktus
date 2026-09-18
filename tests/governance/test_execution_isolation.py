"""ADR-0002, enforced: an execution unit without isolation is refused from autonomy level 3
upwards, and the check fails closed — an unknown level is refused too. The rule is tested as
a table, and the process adapter is shown to apply it before it starts anything."""

from __future__ import annotations

from pathlib import Path

import pytest

from taktus.adapters.driven.configuration import EnvironmentConfiguration
from taktus.adapters.driven.execution import ProcessExecution
from taktus.ports.execution import (
    ExecutionRefused,
    ExecutionUnit,
    Isolation,
    JobRequest,
    ResourceLimits,
    refusal,
)
from taktus.shared.v1 import AutonomyLevel

LIMITS = ResourceLimits(cpus=1, memory_bytes=64 * 1024 * 1024, wall_seconds=10)


@pytest.mark.parametrize(
    ("isolation", "level", "refused"),
    [
        (Isolation.NONE, 1, False),
        (Isolation.NONE, 2, False),
        (Isolation.NONE, 3, True),
        (Isolation.NONE, 4, True),
        (Isolation.NONE, None, True),
        (Isolation.CONTAINER, 3, False),
        (Isolation.CONTAINER, 4, False),
        (Isolation.CONTAINER, None, False),
        (Isolation.CLUSTER, 4, False),
    ],
)
def test_no_isolation_is_refused_from_level_3_and_when_the_level_is_unknown(
    isolation: Isolation, level: AutonomyLevel | None, refused: bool
) -> None:
    why = refusal(isolation, level)
    assert (why is not None) is refused
    if why is not None:
        assert "ADR-0002" in why


@pytest.mark.parametrize("level", [3, 4, None])
async def test_the_process_adapter_refuses_before_starting_anything(
    tmp_path: Path, level: AutonomyLevel | None
) -> None:
    marker = tmp_path / "started"
    unit = ExecutionUnit(name="unit", program=f"touch {marker}", limits=LIMITS)
    execution = ProcessExecution(EnvironmentConfiguration({}), state_dir=tmp_path / "state")
    request = JobRequest(job_id="job-1", unit=unit, autonomy_level=level)
    with pytest.raises(ExecutionRefused, match="ADR-0002"):
        async with execution.launch(request):
            pass
    assert not marker.exists(), "the unit was started although the request was refused"
    assert not (tmp_path / "state").exists(), "nothing was prepared for a refused job"
