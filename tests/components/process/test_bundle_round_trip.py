"""A registered version written back as a bundle registers as the same version under a new name
(UC-4.15 *rolling back is one act*, ADR-0091 §5).

Every bundle the repository ships is read, written back and read again: the steps with their
work, the autonomy statement, the triggers, the inputs, the service level and the limits come
back unchanged; only the version's name, its author and its reason are the rollback's.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from taktus.components.process.application.service.register_version import parse_bundle
from taktus.components.process.domain.service.bundle import bundle_of, next_version

ROOT = Path(__file__).resolve().parents[3]
BUNDLES = sorted((ROOT / "blueprints").glob("*/processes/*.yaml"))


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_a_version_written_back_registers_as_itself_under_a_new_name(path: Path) -> None:
    version = parse_bundle(yaml.safe_load(path.read_text(encoding="utf-8")))
    again = parse_bundle(
        bundle_of(version, as_version="restored", author="idn_ada", reason="rolled back")
    )
    assert again.version == "restored"
    assert (again.author, again.reason) == ("idn_ada", "rolled back")
    assert (
        again.model_copy(
            update={"version": version.version, "author": version.author, "reason": version.reason}
        )
        == version
    )


def test_there_are_bundles_to_write_back() -> None:
    assert len(BUNDLES) >= 5


def test_the_next_version_is_one_above_the_highest_number_and_never_taken() -> None:
    assert next_version(["1", "2", "7"]) == "8"
    assert next_version(["v1", "v2"]) == "3"
    assert next_version(["v1", "3"]) == "4"
    assert next_version(["a", "2"]) == "3"
    assert next_version(["a", "b"]) == "3"
