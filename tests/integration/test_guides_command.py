"""`taktusctl guides` end to end (UC-13.6 §2, ADR-0065): both guides render from this
repository, and a directory of files — the knowledge system of an organisation without one —
receives them without a hand edit being overwritten."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from .test_first_slice import PLAIN, taktusctl

ROOT = Path(__file__).resolve().parents[2]

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.org",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.org",
}


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — our own entry point, fixed arguments
        [taktusctl(), "guides", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env={**os.environ, **PLAIN},
    )


def git(repository: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 — a fixed program and fixed arguments
        ["git", "-C", str(repository), *args],  # noqa: S607 — git on the path
        check=True,
        capture_output=True,
        env={**os.environ, **GIT_IDENTITY},
    )


def test_this_repository_declares_both_guides_and_every_page_renders() -> None:
    manifest = yaml.safe_load((ROOT / "docs" / "guides" / "guides.yaml").read_text("utf-8"))
    guides = {g["id"]: [p["id"] for p in g["pages"]] for g in manifest["guides"]}
    assert guides["administration"] == ["installing", "configuring", "operating", "restoring"]
    assert guides["use"]
    done = cli("check", "--repository", str(ROOT))
    assert done.returncode == 0, done.stderr
    rendered = [line.split()[0] for line in done.stdout.splitlines()[:-1]]
    assert rendered == [f"{g}/{p}" for g, pages in guides.items() for p in pages]


def a_repository(path: Path) -> Path:
    (path / "docs" / "guides").mkdir(parents=True)
    (path / "docs" / "guides" / "guides.yaml").write_text(
        yaml.safe_dump(
            {
                "guides": [
                    {
                        "id": "use",
                        "title": "Using it",
                        "reader": "everybody",
                        "place": ["Handbook"],
                        "pages": [
                            {"id": "asking", "title": "Asking", "parts": [{"file": "ask.md"}]}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (path / "ask.md").write_text("You ask in the chat.\n", encoding="utf-8")
    git(path, "init", "--quiet")
    git(path, "add", "-A")
    git(path, "commit", "--quiet", "-m", "first")
    return path


def test_publish_puts_the_guides_into_files_and_keeps_a_page_edited_there(
    tmp_path: Path,
) -> None:
    repository = a_repository(tmp_path / "repository")
    target = tmp_path / "knowledge"
    first = cli("publish", "--repository", str(repository), "--to", str(target))
    assert first.returncode == 0, first.stderr
    page = target / "Handbook" / "Asking.md"
    contents = target / "Handbook" / "Contents.md"
    assert page.read_text("utf-8").startswith("# Asking\n\nYou ask in the chat.\n")
    assert "- Asking — current" in contents.read_text("utf-8")

    page.write_text(page.read_text("utf-8").replace("in the chat", "in our chat"), "utf-8")
    (repository / "ask.md").write_text("You ask in the chat, or by mail.\n", encoding="utf-8")
    git(repository, "commit", "--quiet", "-am", "second")

    second = cli("publish", "--repository", str(repository), "--to", str(target))
    assert second.returncode == 1, second.stderr
    assert "withheld outdated  Handbook/Asking" in second.stdout
    assert "-You ask in the chat, or by mail.\n+You ask in our chat.\n" in second.stdout
    assert "in our chat" in page.read_text("utf-8")
    assert "- Asking — out of date" in contents.read_text("utf-8")


def test_a_guide_that_cannot_be_rendered_writes_nothing(tmp_path: Path) -> None:
    repository = a_repository(tmp_path / "repository")
    (repository / "ask.md").unlink()
    git(repository, "commit", "--quiet", "-am", "the source is gone")
    target = tmp_path / "knowledge"
    done = cli("publish", "--repository", str(repository), "--to", str(target))
    assert done.returncode == 2
    assert "ask.md does not exist" in done.stderr
    assert not target.exists()
