"""UC-10.2: every administrative act is available through the command line and through the web
app (ADR-0279). The test takes the inventory of administrative acts and finds each one in both:
the command line's command, the HTTP surface's operation the web app calls, and the web app's
page with the act's form or list marked by its name."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer
import yaml

from taktus.adapters.driving.cli.main import app
from taktus.adapters.driving.inventory import ACTS, Act

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))
WEB = ROOT / "web" / "src"
CLI: Any = typer.main.get_command(app)
MARKED = "\n".join(p.read_text(encoding="utf-8") for p in sorted(WEB.rglob("*.svelte")))


def command(words: tuple[str, ...]) -> Any:
    """The command line's command for the words, or None."""
    found: Any = CLI
    for word in words:
        found = getattr(found, "commands", {}).get(word)
        if found is None:
            return None
    return found


def marked(act: Act) -> bool:
    """Whether a form or a list of the web app is marked with the act's name."""
    return f'data-act="{act.name}"' in MARKED


def test_the_inventory_names_each_act_once() -> None:
    names = [a.name for a in ACTS]
    assert len(names) == len(set(names))
    assert len(ACTS) >= 20


@pytest.mark.parametrize("act", ACTS, ids=[a.name for a in ACTS])
def test_every_administrative_act_is_on_the_command_line_and_in_the_web_app(act: Act) -> None:
    assert command(act.cli) is not None, f"`taktusctl {' '.join(act.cli)}` does not exist"
    operations = OPENAPI["paths"].get(act.path, {})
    assert act.method in operations, f"{act.method.upper()} {act.path} is not on the surface"
    page = WEB / "routes" / act.page / "+page.svelte"
    assert page.is_file(), f"the web app has no page #/{act.page}"
    assert marked(act), f"no form or list of the web app is marked data-act={act.name!r}"
