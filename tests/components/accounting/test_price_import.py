"""An open price list becomes a price table version; what cannot be mapped is named (#327)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from taktus.adapters.driving.cli.main import app
from taktus.components.accounting.domain.service.price_import import import_prices

LIST = {
    "sample_spec": {"input_cost_per_token": 0.0},
    "model-a": {
        "input_cost_per_token": 2.5e-06,
        "output_cost_per_token": 1e-05,
        "cache_read_input_token_cost": 1.25e-06,
        "cache_creation_input_token_cost": 3e-06,
    },
    "model-b": {"input_cost_per_token": 1e-07},
    "no-price": {"mode": "chat"},
    "bad name!": {"input_cost_per_token": 1e-06},
}
WHEN = datetime(2026, 10, 20, tzinfo=UTC)


def test_every_kind_is_priced_per_million_tokens_and_the_rest_is_named() -> None:
    imported = import_prices(LIST, version="v1", valid_from=WHEN, currency="usd", source="s")
    assert imported.table.prices["model-a"] == {
        "input": 2.5,
        "output": 10.0,
        "cache_read": 1.25,
        "cache_write": 3.0,
    }
    assert imported.table.prices["model-b"] == {"input": 0.1}
    assert "sample_spec" not in imported.table.prices
    assert [u.split(":")[0] for u in imported.unmapped] == ["no-price", "bad name!"]


def test_a_list_that_maps_to_nothing_is_refused() -> None:
    with pytest.raises(ValueError):
        import_prices({"x": {}}, version="v1", valid_from=WHEN, currency="usd", source="s")


def test_the_command_writes_the_table_and_never_overwrites_it(tmp_path: Path) -> None:
    source = tmp_path / "list.json"
    source.write_text(json.dumps(LIST), encoding="utf-8")
    target = tmp_path / "table.json"
    args = ["prices", "import", str(source), "--version", "v1", "--output", str(target)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "unmapped no-price" in result.output
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == "v1"
    assert CliRunner().invoke(app, args).exit_code == 2
