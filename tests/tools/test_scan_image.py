"""The scan of every published image (ADR-0173 §2, §4), against a stand-in scanner: what it is
asked, once per platform, and how its answer is read — findings, a pass, or an error, which is
never taken for either. The real scanner against a known-vulnerable image runs in the image
workflow's job `proof`, before anything is built."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "scan_image.sh"
IMAGE = "registry.invalid/o/taktus@sha256:" + "0" * 64

# Exits with the status FAKE_STATUS names for the platform it is asked about
# (`FAKE_STATUS=linux/arm64=2,*=0`) and logs each call's arguments, one line each.
FAKE = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
platform=""
while [ $# -gt 0 ]; do
    [ "$1" = "--platform" ] && platform=$2
    shift
done
status=0
for rule in $(echo "$FAKE_STATUS" | tr , ' '); do
    case "$rule" in
        "$platform="*) status=${rule#*=}; break ;;
        "*="*) status=${rule#*=} ;;
    esac
done
exit "$status"
"""


def scan(tmp_path: Path, status: str, *args: str) -> tuple[int, str, list[str]]:
    fake = tmp_path / "grype"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls"
    env = {**os.environ, "TAKTUS_GRYPE": str(fake), "FAKE_LOG": str(log), "FAKE_STATUS": status}
    # A fixed script of this repository and arguments assembled in this file.
    completed = subprocess.run(  # noqa: S603
        [str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60, check=False
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed.returncode, completed.stdout + completed.stderr, calls


def test_a_clean_image_passes_and_the_scanner_is_asked_for_fixed_high_findings(
    tmp_path: Path,
) -> None:
    code, output, [call] = scan(tmp_path, "*=0", IMAGE)
    assert code == 0, output
    assert call.startswith(f"registry:{IMAGE} --platform linux/amd64 ")
    assert "--only-fixed" in call
    assert "--fail-on high" in call
    assert f"--config {ROOT / 'deploy' / 'images' / 'grype.yaml'}" in call


def test_findings_on_one_platform_fail_the_scan_and_every_platform_is_scanned(
    tmp_path: Path,
) -> None:
    code, output, calls = scan(tmp_path, "linux/arm64=2,*=0", IMAGE, "linux/amd64,linux/arm64")
    assert code == 1
    assert len(calls) == 2
    assert "linux/arm64) has a fixed high or critical vulnerability" in output


def test_an_error_of_the_scanner_fails_the_scan(tmp_path: Path) -> None:
    code, output, _ = scan(tmp_path, "*=1", IMAGE)
    assert code == 1
    assert "stopped with error 1" in output


@pytest.mark.parametrize(
    ("status", "expected", "said"),
    [
        ("*=2", 0, "failed on findings, as it must"),
        ("*=0", 1, "is no gate"),
        ("*=1", 1, "not on findings"),
    ],
)
def test_the_proof_passes_only_when_the_scan_fails_on_findings(
    tmp_path: Path, status: str, expected: int, said: str
) -> None:
    code, output, _ = scan(tmp_path, status, "--expect-findings", IMAGE)
    assert code == expected, output
    assert said in output


def test_without_the_scanner_the_scan_fails_and_says_how_to_install_it(tmp_path: Path) -> None:
    env = {**os.environ, "TAKTUS_GRYPE": str(tmp_path / "absent")}
    completed = subprocess.run(  # noqa: S603
        [str(SCRIPT), IMAGE], capture_output=True, text=True, env=env, timeout=60, check=False
    )
    assert completed.returncode == 1
    assert "make image-tools" in completed.stderr
