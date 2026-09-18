"""Fakes of the ports for application tests: deterministic time and identifiers, a scripted
worker, a connector with a memory, a model with a script. No mocks — every fake is a small real
implementation of its port."""

from fakes.clock import FakeClock, FakeIdentifiers
from fakes.connector import FakeConnector, failure
from fakes.model import FakeModel
from fakes.worker import FakeWorker, InnerStep

__all__ = [
    "FakeClock",
    "FakeConnector",
    "FakeIdentifiers",
    "FakeModel",
    "FakeWorker",
    "InnerStep",
    "failure",
]
