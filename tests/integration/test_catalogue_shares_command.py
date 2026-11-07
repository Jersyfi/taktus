"""`taktusctl catalogue share`, `shares`, `withdraw`, `use` and `bind-credential` (ADR-0246,
ADR-0247; UC-8.6, UC-8.8): a model is shared with one team, seen there and not by another,
withdrawn only with its removal verdict known; a caller's own credential is bound by name."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl

TENANT = "default"


def cli(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_a_model_shared_with_one_team_is_seen_there_and_withdrawn_only_with_a_verdict(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    for who, path in (("idn_ann", "default/support"), ("idn_bob", "default/sales")):
        added = cli(state, "identity", "add", who, "--org-path", path)
        assert added.returncode == 0, added.stdout + added.stderr

    incomplete = cli(
        state,
        "catalogue",
        "share",
        "model",
        "model.local",
        "--purpose",
        "Drafts replies",
        "--circle",
        "default/support",
        "--identity",
        "idn_ann",
    )
    assert incomplete.returncode == 1
    assert "where it processes data" in incomplete.stderr

    shared = cli(
        state,
        "catalogue",
        "share",
        "model",
        "model.local",
        "--purpose",
        "Drafts replies",
        "--circle",
        "default/support",
        "--location",
        "own",
        "--cost-model",
        "per_hardware_time",
        "--origin",
        "provided",
        "--identity",
        "idn_ann",
    )
    assert shared.returncode == 0, shared.stdout + shared.stderr
    assert "shared model:model.local with default/support" in shared.stdout

    ann = cli(state, "catalogue", "shares", "--identity", "idn_ann")
    bob = cli(state, "catalogue", "shares", "--identity", "idn_bob")
    assert "model:model.local" in ann.stdout and "processes own" in ann.stdout
    assert "nothing is shared with you" in bob.stdout

    refused = cli(state, "catalogue", "withdraw", "model", "model.local", "--identity", "idn_ann")
    assert refused.returncode == 1 and "no_verdict" in refused.stderr

    used = cli(state, "catalogue", "use", "model", "model.local", "--identity", "idn_ann")
    assert used.returncode == 0 and "0 calls, 0 of them yours" in used.stdout

    bound = cli(
        state,
        "catalogue",
        "bind-credential",
        "idn_bob",
        "TICKETS_TOKEN",
        "BOB",
        "--identity",
        "idn_ann",
    )
    assert bound.returncode == 0, bound.stdout + bound.stderr
    assert "TAKTUS_CREDENTIAL_TICKETS_TOKEN_BOB_FILE" in bound.stdout
