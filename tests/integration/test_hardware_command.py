"""`taktusctl hardware` end to end (ADR-0284, UC-10.1): the machine it runs on shown — its
processors, memory and accelerators, or why they could not be looked for — and for each
configured model what it needs and whether this machine has it. No state, no database."""

from __future__ import annotations

import json
import os
import subprocess

from .test_first_slice import PLAIN, taktusctl

LOCAL = {
    "TAKTUS_MODELS": "small,huge,remote",
    "TAKTUS_MODELS_SMALL_ENDPOINT": "http://127.0.0.1:9/v1",
    "TAKTUS_MODELS_SMALL_NAME": "small",
    "TAKTUS_MODELS_SMALL_LOCATION": "own",
    "TAKTUS_MODELS_SMALL_NEEDS": "processors=1,memory=1MiB",
    "TAKTUS_MODELS_HUGE_ENDPOINT": "http://127.0.0.1:9/v1",
    "TAKTUS_MODELS_HUGE_NAME": "huge",
    "TAKTUS_MODELS_HUGE_LOCATION": "own",
    "TAKTUS_MODELS_HUGE_NEEDS": "processors=100000",
    "TAKTUS_MODELS_REMOTE_ENDPOINT": "http://127.0.0.1:9/v1",
    "TAKTUS_MODELS_REMOTE_NAME": "remote",
    "TAKTUS_MODELS_REMOTE_LOCATION": "eu",
}


def hardware(*args: str, **environment: str) -> subprocess.CompletedProcess[str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("TAKTUS_")}
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "hardware", *args],
        capture_output=True,
        text=True,
        env={**inherited, **PLAIN, **environment},
        check=False,
    )


def test_the_machine_is_shown_and_each_local_model_against_it() -> None:
    shown = hardware(**LOCAL)
    assert shown.returncode == 1, shown.stdout + shown.stderr  # one local model is short
    out = shown.stdout
    assert f"processors    {os.cpu_count()}" in out
    assert "memory" in out and "accelerator" in out
    assert "[fits] model.small: local" in out
    assert "[short] model.huge: local" in out and "processors at least 100000: missing" in out
    assert "[elsewhere] model.remote: runs at location eu" in out
    document = json.loads(hardware("--json", **LOCAL).stdout)
    assert document["adapter"] == "platform.hardware"
    assert document["inventory"]["processors"]["count"] == os.cpu_count()
    assert [m["fit"] for m in document["models"]] == ["fits", "short", "elsewhere"]


def test_without_a_model_the_machine_is_shown_and_nothing_is_short() -> None:
    shown = hardware()
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert "none configured" in shown.stdout


def test_a_wrong_declaration_is_refused_naming_its_setting() -> None:
    shown = hardware(**{**LOCAL, "TAKTUS_MODELS_HUGE_NEEDS": "gpu=yes"})
    assert shown.returncode == 2
    assert "TAKTUS_MODELS_HUGE_NEEDS" in shown.stderr
