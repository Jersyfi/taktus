"""`taktusctl owner-channel`: a tenant's owner-facing channel configured from a file with a
shipped phrasebook, shown, and refused when it does not hold (ADR-0045)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .test_first_slice import PLAIN, taktusctl


def owner_channel(state: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "owner-channel", *arguments, "--state-dir", str(state)],
        capture_output=True,
        text=True,
        env={**os.environ, **PLAIN},
        check=False,
    )


def test_an_operator_configures_and_shows_the_owner_facing_channel(tmp_path: Path) -> None:
    state = tmp_path / "state"
    missing = owner_channel(state, "show")
    assert missing.returncode == 1 and "configured no owner-facing channel" in missing.stderr

    configuration = tmp_path / "owner-channel.json"
    configuration.write_text(
        json.dumps(
            {
                "owner": "idn_owner",
                "named": ["idn_deputy"],
                "channel": "channel.chat",
                "address": "D0000000001",
                "language": "de",
            }
        ),
        encoding="utf-8",
    )
    configured = owner_channel(state, "set", str(configuration), "--identity", "idn_owner")
    assert configured.returncode == 0, configured.stdout + configured.stderr
    assert "configured: channel.chat, in de, 1 named" in configured.stdout

    shown = owner_channel(state, "show")
    assert shown.returncode == 0, shown.stderr
    document = json.loads(shown.stdout)
    assert document["owner"] == "idn_owner" and document["phrasebook"]["language"] == "de"
    assert document["configured_by"] == "idn_owner"

    configuration.write_text(json.dumps({"owner": "idn_owner", "language": "xx"}))
    refused = owner_channel(state, "set", str(configuration))
    assert refused.returncode == 2 and "ships none" in refused.stderr
    assert json.loads(owner_channel(state, "show").stdout)["address"] == "D0000000001"
