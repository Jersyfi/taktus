"""The record of what one run of the image workflow published (ADR-0173 §6): every image by
its digest, and the chart's values that pin them; anything else is refused, writing nothing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import image_digests  # noqa: E402 — a script under tools/, found through the line above


def digest(number: int) -> str:
    return f"sha256:{number:064x}"


def write(directory: Path, name: str, number: int, *, tag: str = "1.0.0") -> None:
    entry = {"name": name, "repository": f"registry.invalid/o/{name}", "tag": tag}
    entry["digest"] = digest(number)
    (directory / name).write_text(json.dumps(entry), encoding="utf-8")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    directory = tmp_path / "in"
    directory.mkdir()
    for number, name in enumerate(
        ["taktus", "taktus-backup", "taktus-connector-github", "taktus-worker-script"], start=1
    ):
        write(directory, name, number)
    return directory


def test_every_image_is_listed_by_its_digest(source: Path, tmp_path: Path) -> None:
    assert image_digests.main(["--in", str(source), "--out", str(tmp_path / "out")]) == 0
    listed = json.loads((tmp_path / "out" / "images.json").read_text(encoding="utf-8"))
    assert [i["name"] for i in listed] == sorted(i["name"] for i in listed)
    assert listed[0] == {
        "name": "taktus",
        "repository": "registry.invalid/o/taktus",
        "tag": "1.0.0",
        "digest": digest(1),
        "reference": f"registry.invalid/o/taktus:1.0.0@{digest(1)}",
    }


def test_the_values_pin_what_the_chart_derives_and_name_the_workers(
    source: Path, tmp_path: Path
) -> None:
    image_digests.record(source, tmp_path / "out")
    text = (tmp_path / "out" / "digests.values.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(text) == {
        "image": {"tag": "1.0.0", "digest": digest(1)},
        "backup": {"image": {"digest": digest(2)}},
        "connectors": {"digests": {"github": digest(3)}},
    }
    assert f"taktus-worker-script: registry.invalid/o/taktus-worker-script:1.0.0@{digest(4)}" in (
        text
    )


@pytest.mark.parametrize(
    ("content", "complaint"),
    [
        ("not json", "not JSON"),
        ('{"name": "taktus"}', "exactly"),
        (
            '{"name": "taktus", "repository": "r", "tag": "1", "digest": "sha256:abc"}',
            "is not sha256",
        ),
        (
            '{"name": "other", "repository": "r", "tag": "1", "digest": "sha256:' + "0" * 64 + '"}',
            "no image name",
        ),
        ('{"name": "taktus", "repository": "", "tag": "1", "digest": "x"}', "not empty"),
    ],
)
def test_a_record_of_another_form_is_refused_and_nothing_is_written(
    source: Path, tmp_path: Path, content: str, complaint: str
) -> None:
    (source / "zz-broken").write_text(content, encoding="utf-8")
    with pytest.raises(image_digests.Refused, match=complaint):
        image_digests.record(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_one_run_publishes_one_tag(source: Path, tmp_path: Path) -> None:
    write(source, "taktus-connector-slack", 9, tag="0.9.0")
    with pytest.raises(image_digests.Refused, match="one tag"):
        image_digests.record(source, tmp_path / "out")


def test_an_image_recorded_twice_is_refused(source: Path, tmp_path: Path) -> None:
    (source / "again").write_text((source / "taktus").read_text(encoding="utf-8"), "utf-8")
    with pytest.raises(image_digests.Refused, match="twice"):
        image_digests.record(source, tmp_path / "out")


def test_nothing_recorded_is_refused(tmp_path: Path) -> None:
    (tmp_path / "in").mkdir()
    assert image_digests.main(["--in", str(tmp_path / "in"), "--out", str(tmp_path / "o")]) == 1
