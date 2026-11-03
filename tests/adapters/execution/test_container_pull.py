"""The container engine pulls an image by its digest when its reference carries one (ADR-0173
§7): `repo:tag@sha256:<hex>` is the form the chart renders and an operator writes."""

from __future__ import annotations

import pytest

from taktus.adapters.driven.execution.container.engine import pull_parameters

DIGEST = "sha256:" + "a" * 64


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("python:3.13-slim", {"fromImage": "python", "tag": "3.13-slim"}),
        ("python", {"fromImage": "python", "tag": "latest"}),
        ("registry:5000/taktus", {"fromImage": "registry:5000/taktus", "tag": "latest"}),
        ("registry:5000/taktus:1.0.0", {"fromImage": "registry:5000/taktus", "tag": "1.0.0"}),
        (f"python:3.13-slim@{DIGEST}", {"fromImage": "python", "tag": DIGEST}),
        (f"python@{DIGEST}", {"fromImage": "python", "tag": DIGEST}),
        (f"registry:5000/taktus@{DIGEST}", {"fromImage": "registry:5000/taktus", "tag": DIGEST}),
        (
            f"registry:5000/taktus:1.0.0@{DIGEST}",
            {"fromImage": "registry:5000/taktus", "tag": DIGEST},
        ),
    ],
)
def test_a_reference_is_pulled_by_its_tag_or_by_its_digest(
    reference: str, expected: dict[str, str]
) -> None:
    assert pull_parameters(reference) == expected
