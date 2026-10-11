"""The backup program, loaded by its path: it ships in its own image and is no package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PATH = Path(__file__).resolve().parents[2] / "deploy" / "backup" / "backup.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("taktus_backup", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its module up while it is created
    spec.loader.exec_module(module)
    return module


backup = load()
