"""A composed case is assembled from the catalogue's entries, named by capability (UC-12.3 §2,
ADR-0003).

The composed cases of this repository are the gallery's — a family organiser, a club's
administration, a small business's follow-up — and the knowledge assistants K-01 and K-02, the
pattern of a channel, an agent, knowledge, tools and a process. Each names what it calls by
capability and operation, never by product: every operation is one a connector of this
repository declares or the instance serves about itself, and none of them names a product the
architecture tests know. That a composed case runs as an ordinary process
version, in the ledger and under its autonomy statement, is
`test_rollout_channels.py::test_the_same_message_is_a_command_in_a_command_channel_and_answered_in_a_rollout_one`.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from architecture.test_core_is_technology_free import PRODUCT

from composition.test_software_operations import CONNECTORS, declared_operations

ROOT = Path(__file__).resolve().parents[2]
CASES = sorted(
    [
        *(ROOT / "blueprints" / "gallery").glob("*/processes/*.yaml"),
        *(ROOT / "blueprints" / "knowledge" / "processes").glob("*.yaml"),
    ]
)


def catalogue() -> set[str]:
    """Every operation a connector of this repository declares, as its declaration states it,
    and what the instance serves about itself."""
    served = declared_operations()
    for path in sorted(CONNECTORS.glob("*/declaration.py")):
        module = importlib.import_module(f"taktus_connectors.{path.parent.name}.declaration")
        served |= {op["name"] for op in getattr(module, "OPERATIONS", ())}
    return served


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_a_composed_case_calls_only_operations_a_connector_of_the_catalogue_declares(
    path: Path,
) -> None:
    served = catalogue()
    text = path.read_text(encoding="utf-8")
    for operation in re.findall(r"operation: ([a-z][a-z0-9_.]+)", text):
        assert operation in served, f"{path.name} calls {operation}, which no connector serves"


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_a_composed_case_names_no_product(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = PRODUCT.search(line)
        assert match is None, f"{path.name}:{number} names the product {match.group(0)!r}"


def test_the_cases_are_the_examples_the_use_case_names() -> None:
    assert {p.parent.parent.name for p in CASES if "gallery" in p.parts} == {
        "club",
        "family",
        "small-business",
    }
    assert {p.stem[:4] for p in CASES if "knowledge" in p.parts} == {"K-01", "K-02"}
