"""The secret files of a one-server install come from a store the operator chooses (ADR-0187).

`deploy/docker/secret_store.py` runs the store's own command per secret and writes the files
Taktus reads. The store here is a stand-in: a script that prints the value a JSON file holds
for a reference, and fails for one it does not hold. What is proven: a rotation in the store
reaches the file without a person and in place, so that a mounted file sees it; a store that
fails or is gone leaves every file as it was; without a configuration nothing changes; no value
reaches the program's output.
"""

from __future__ import annotations

import importlib.util
import json
import secrets
import sys
from pathlib import Path
from types import ModuleType

import pytest

DOCKER = Path(__file__).resolve().parents[2] / "deploy" / "docker"

STAND_IN = """
import json, sys
values = json.load(open(sys.argv[1]))
reference = sys.argv[2]
if reference not in values:
    sys.exit(1)
print(values[reference])
"""


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("taktus_secret_store", DOCKER / "secret_store.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


store_program = load()


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.values = root / "store.json"
        self.script = root / "store_cli.py"
        self.script.write_text(STAND_IN, encoding="utf-8")
        self.config = root / "secret-store.json"
        self.directory = root / "secrets"
        self.config.write_text(
            json.dumps(
                {
                    "command": [sys.executable, str(self.script), str(self.values), "{reference}"],
                    "secrets": [
                        {"file": "payments_token", "reference": "taktus/payments"},
                        {"file": "model_costs_token", "reference": "taktus/model-costs"},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def store(self, **values: str) -> None:
        self.values.write_text(json.dumps(values), encoding="utf-8")

    def run(self, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
        code = store_program.main(
            ["--config", str(self.config), "--directory", str(self.directory)]
        )
        captured = capsys.readouterr()
        return code, captured.out + captured.err

    def file(self, name: str) -> str:
        return (self.directory / name).read_text(encoding="utf-8")


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_the_store_fills_the_files_and_a_rotation_reaches_them_in_place(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = secrets.token_hex(16), secrets.token_hex(16)
    world.store(**{"taktus/payments": first, "taktus/model-costs": second})
    code, out = world.run(capsys)
    assert code == 0
    assert world.file("payments_token") == first + "\n"
    assert world.file("model_costs_token") == second + "\n"
    assert (world.directory / "payments_token").stat().st_mode & 0o777 == 0o644
    assert world.directory.stat().st_mode & 0o777 == 0o700
    inode = (world.directory / "payments_token").stat().st_ino

    rotated = secrets.token_hex(8)  # shorter than before: the rest of the old value is gone
    world.store(**{"taktus/payments": rotated, "taktus/model-costs": second})
    code, again = world.run(capsys)
    assert code == 0
    assert world.file("payments_token") == rotated + "\n"
    assert (world.directory / "payments_token").stat().st_ino == inode, "written in place"
    assert "payments_token: written" in again
    assert "model_costs_token" not in again, "an unchanged value is not written again"
    for value in (first, second, rotated):
        assert value not in out + again


def test_a_store_that_fails_or_is_gone_leaves_every_file_as_it_was(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    kept = secrets.token_hex(16)
    world.store(**{"taktus/payments": kept, "taktus/model-costs": secrets.token_hex(16)})
    assert world.run(capsys)[0] == 0
    world.store(**{"taktus/model-costs": secrets.token_hex(16)})  # the payment key is gone
    code, out = world.run(capsys)
    assert code == 1
    assert world.file("payments_token") == kept + "\n"
    assert "payments_token: not read; the file is left as it was" in out
    world.script.unlink()  # the store's tool removed altogether
    code, _ = world.run(capsys)
    assert code == 1
    assert world.file("payments_token") == kept + "\n"


def test_without_a_configuration_the_files_are_the_operators(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    """The removal test of ADR-0187 §4: no store, nothing changes."""
    world.directory.mkdir()
    by_hand = world.directory / "payments_token"
    by_hand.write_text("written by hand\n", encoding="utf-8")
    world.config.unlink()
    code, out = world.run(capsys)
    assert code == 0 and out == ""
    assert by_hand.read_text(encoding="utf-8") == "written by hand\n"


@pytest.mark.parametrize(
    ("document", "fault"),
    [
        ({"command": ["cli", "read"], "secrets": [{"file": "a", "reference": "r"}]}, "{reference}"),
        ({"command": "cli {reference}", "secrets": [{"file": "a", "reference": "r"}]}, "list"),
        ({"command": ["cli", "{reference}"], "secrets": []}, "at least one"),
        ({"command": ["cli", "{reference}"], "secrets": [{"file": "../a", "reference": "r"}]},
         "no path"),
        (
            {
                "command": ["cli", "{reference}"],
                "secrets": [{"file": "a", "reference": "r"}, {"file": "a", "reference": "s"}],
            },
            "named twice",
        ),
        ({"command": ["cli", "{reference}"], "secrets": [{"file": "a", "value": "x"}]},
         "nothing else"),
    ],
)  # fmt: skip
def test_a_configuration_that_cannot_be_used_is_refused(document: object, fault: str) -> None:
    with pytest.raises(store_program.Refused, match=fault):
        store_program.load(document)


def test_the_example_is_a_configuration_the_program_takes() -> None:
    example = json.loads((DOCKER / "secret-store.example.json").read_text(encoding="utf-8"))
    store = store_program.load(example)
    assert store.argv(store.secrets[0])[-1] == "taktus/payments/token"
