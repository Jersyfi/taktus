"""The ports the tests' servers take (`tests/fakes/ports.py`): every parallel worker of a session
counts through a range of its own, however many workers `-n auto` starts, and every range ends
below the system's own (#360). With fourteen workers and ranges sized for eight, worker 8 once
counted through worker 0's ports, and servers of two tests answered each other."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType

import pytest


def load(monkeypatch: pytest.MonkeyPatch, worker: int, count: int | None) -> ModuleType:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", f"gw{worker}")
    if count is None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER_COUNT", raising=False)
    else:
        monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", str(count))
    sys.modules.pop("fakes.ports", None)
    return importlib.import_module("fakes.ports")


@pytest.fixture(autouse=True)
def restore() -> Iterator[None]:
    """The session's own module back, so that every later test counts on its one cycle."""
    original = importlib.import_module("fakes.ports")
    yield
    sys.modules["fakes.ports"] = original


@pytest.mark.parametrize("count", [1, 2, 8, 14, 32])
def test_each_worker_has_a_range_of_its_own_below_the_system_s(
    monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    ranges = []
    for worker in range(count):
        ports = load(monkeypatch, worker, count)
        ranges.append(range(ports._start, ports._start + ports.SPAN))
    taken = [port for span in ranges for port in span]
    assert len(taken) == len(set(taken)), "two workers share a port"
    assert min(taken) >= ports.BASE and max(taken) < ports.TOP


def test_a_port_it_gives_is_in_the_worker_s_range(monkeypatch: pytest.MonkeyPatch) -> None:
    ports = load(monkeypatch, 3, 14)
    port = ports.free_port()
    assert ports._start <= port < ports._start + ports.SPAN
