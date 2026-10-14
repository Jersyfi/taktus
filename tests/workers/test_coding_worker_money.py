"""The coding worker prices every step at its own price table (DEC-0202).

The table is the contract's shape (`contracts/model/v1`, PriceTable), shipped beside the worker
and replaceable by its operator. A model is found as the agent names it, with its snapshot
date or without; one the table does not name is priced at the dearest price of each kind, so
that a money limit halts early rather than late. The worker is a separate deployable, loaded
by its path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from taktus.ports.model import PriceTable

WORKER = Path(__file__).resolve().parents[2] / "workers" / "claudecode" / "worker.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worker_claudecode_money", WORKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_shipped_price_table_is_the_contracts_shape() -> None:
    table = load().load_prices(None)
    PriceTable.model_validate(table)
    assert table["currency"] == "usd" and table["unit_tokens"] == 1_000_000


def test_a_model_is_priced_by_its_name_with_or_without_its_date() -> None:
    worker = load()
    table = worker.load_prices(None)
    dated, known = worker.prices_of("claude-haiku-4-5-20251001", table)
    assert known and dated == {"input": 1.0, "cache_read": 0.1, "cache_write": 2.0, "output": 5.0}
    tokens = {"claude-haiku-4-5-20251001": {"input": 1000, "cache_read": 1_000_000, "output": 0}}
    assert worker.money_of(tokens, table) == pytest.approx(0.001 + 0.1)


def test_a_model_the_table_does_not_name_is_priced_at_the_dearest_of_each_kind() -> None:
    worker = load()
    table = worker.load_prices(None)
    prices, known = worker.prices_of("a-model-nobody-priced", table)
    assert not known
    for kind in ("input", "cache_read", "cache_write", "output"):
        assert prices[kind] == max(p.get(kind, 0.0) for p in table["prices"].values())


def test_an_operator_replaces_the_table_by_a_file_or_inline(tmp_path: Path) -> None:
    worker = load()
    own = {
        "version": "own-1",
        "valid_from": "2026-10-15T00:00:00Z",
        "currency": "eur",
        "unit_tokens": 1000,
        "source": "a test",
        "prices": {"m": {"input": 1.0}},
    }
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(own))
    assert worker.load_prices(str(path))["version"] == "own-1"
    assert worker.load_prices(json.dumps(own))["currency"] == "eur"
    with pytest.raises(ValueError, match="price kinds"):
        worker.load_prices(json.dumps({**own, "prices": {"m": {"lunch": 1.0}}}))
    with pytest.raises(ValueError, match="cannot be read"):
        worker.load_prices(str(tmp_path / "missing.json"))


def test_a_table_in_another_currency_stops_the_worker_at_its_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = load()
    table = {**worker.load_prices(None), "currency": "eur"}
    monkeypatch.setenv("CODING_AGENT_PRICE_TABLE", json.dumps(table))
    options = worker.parse_args(["--auth", "api-key", "--state-dir", str(tmp_path)])
    with pytest.raises(ValueError, match="prices in eur"):
        worker.Worker(options)
