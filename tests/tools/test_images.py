"""The test images are built only when their content changed, and a build that hangs says where.

`tests/images.py` against a fake `docker` on the path: a shell script that records every call
and plays the engine's part — an image with a given label, a build that prints plain progress
and then stops moving, one that keeps printing past its bound, one that fails. No Docker needed.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import images
import pytest

STEPS = """\
#0 building with "desktop-linux" instance using docker driver
#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 312B done
#1 DONE 0.0s
#2 [internal] load metadata for docker.io/library/python:3.13-slim-bookworm
"""


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `docker` that appends its arguments to calls.log and behaves as FAKE_* say: the label
    `image inspect` reports, and what `build` prints and does."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    script = bin_dir / "docker"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{calls}"\n'
        'if [ "$1" = image ]; then\n'
        '  if [ -z "$FAKE_LABEL" ]; then echo "no such image" >&2; exit 1; fi\n'
        '  printf \'{"Labels": {"%s": "%s"}}\\n\' "$FAKE_LABEL_KEY" "$FAKE_LABEL"; exit 0\n'
        "fi\n"
        'if [ "$1" = build ]; then\n'
        '  printf "%s" "$FAKE_BUILD_OUTPUT"\n'
        '  case "$FAKE_BUILD" in\n'
        "    stall) exec sleep 30 ;;\n"
        '    busy) while true; do echo "#2 0.1 still resolving"; sleep 0.05; done ;;\n'
        "    fail) exit 1 ;;\n"
        "    *) exit 0 ;;\n"
        "  esac\n"
        "fi\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LABEL_KEY", images.LABEL)
    monkeypatch.setenv("FAKE_LABEL", "")
    monkeypatch.setenv("FAKE_BUILD_OUTPUT", STEPS)
    monkeypatch.setenv("FAKE_BUILD", "ok")
    monkeypatch.setattr(images, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(images, "_session", images._Session())
    return calls


def an_image(tmp_path: Path, *, timeout: float = 10.0, stall: float = 10.0) -> images.Image:
    context = tmp_path / "context"
    (context / "app" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (context / "Dockerfile").write_text(
        "FROM python:3.13-slim-bookworm AS base\n"
        "COPY --chown=unit:unit app/worker.py \\\n    /app/worker.py\n"
        "COPY app ./app\n"
        "FROM base\n"
        "COPY --from=base /app /app\n",
        encoding="utf-8",
    )
    (context / "app" / "worker.py").write_text("print('one')\n", encoding="utf-8")
    (context / "app" / "__pycache__" / "worker.pyc").write_bytes(b"\0")
    (context / "unrelated.txt").write_text("not copied\n", encoding="utf-8")
    (context / ".dockerignore").write_text("**/__pycache__\n", encoding="utf-8")
    return images.Image("fake:test", context / "Dockerfile", context, timeout=timeout, stall=stall)


def builds(calls: Path) -> list[str]:
    if not calls.exists():
        return []
    return [line for line in calls.read_text().splitlines() if line.startswith("build")]


def test_an_image_whose_label_matches_its_content_is_not_built(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = an_image(tmp_path)
    digest = images.content_digest(image)
    monkeypatch.setenv("FAKE_LABEL", digest)
    assert images.ensure(image) == f"fake:test-{digest[:12]}", "the tag that names the content"
    assert builds(fake_docker) == [], "docker build was not invoked at all"
    assert fake_docker.read_text().splitlines() == [
        f"image inspect --format {{{{json .Config}}}} fake:test-{digest[:12]}"
    ], "one question to the engine, by the content tag"
    assert images.ensure(image) == f"fake:test-{digest[:12]}"
    assert len(fake_docker.read_text().splitlines()) == 1, "and the engine asked once a session"


def test_an_image_whose_content_changed_is_built_with_plain_progress_and_its_label(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = an_image(tmp_path)
    monkeypatch.setenv("FAKE_LABEL", "an-older-digest")
    digest = images.content_digest(image)
    assert images.ensure(image) == f"fake:test-{digest[:12]}"
    (call,) = builds(fake_docker)
    assert "--progress=plain" in call and "-q" not in call.split()
    assert f"--label {images.LABEL}={digest}" in call
    assert f"-t fake:test-{digest[:12]} -t fake:test " in call, "the content tag and the plain one"


def test_the_digest_follows_what_the_dockerfile_copies_and_nothing_else(tmp_path: Path) -> None:
    image = an_image(tmp_path)
    before = images.content_digest(image)
    (image.context / "unrelated.txt").write_text("changed\n", encoding="utf-8")
    (image.context / "app" / "__pycache__" / "worker.pyc").write_bytes(b"\1")
    assert images.content_digest(image) == before, "an uncopied or ignored file changes nothing"
    (image.context / "app" / "worker.py").write_text("print('two')\n", encoding="utf-8")
    assert images.content_digest(image) != before, "a copied file changes the digest"
    assert images.copied_sources(image.dockerfile.read_text()) == ["app/worker.py", "app"]


def test_a_build_that_stops_moving_is_stopped_and_says_where(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = an_image(tmp_path, timeout=10.0, stall=0.5)
    monkeypatch.setenv("FAKE_BUILD", "stall")
    started = time.monotonic()
    with pytest.raises(images.ImageBuildError) as raised:
        images.ensure(image)
    assert time.monotonic() - started < 5, "stopped at the stall, not at the bound"
    message = str(raised.value)
    assert raised.value.hung
    assert "the test image fake:test did not build: stalled — no output for 0.5 s" in message
    assert (
        "steps started and not finished: "
        "#2 [internal] load metadata for docker.io/library/python:3.13-slim-bookworm" in message
    )
    assert "#1 [internal] load build definition" not in message.split("last lines")[0]
    assert f"full log: {tmp_path / 'logs' / 'fake-test.log'}" in message
    assert len(builds(fake_docker)) == 1, "a hang is not retried"


def test_a_build_that_keeps_printing_past_its_bound_is_stopped_at_the_bound(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = an_image(tmp_path, timeout=1.0, stall=10.0)
    monkeypatch.setenv("FAKE_BUILD", "busy")
    with pytest.raises(images.ImageBuildError) as raised:
        images.ensure(image)
    message = str(raised.value)
    assert "timed out at its bound of 1 s" in message
    assert "#2 [internal] load metadata" in message and "#2 0.1 still resolving" in message


def test_a_failed_build_is_retried_once_and_then_reported_once(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = an_image(tmp_path)
    monkeypatch.setenv("FAKE_BUILD", "fail")
    with pytest.raises(images.ImageBuildError) as first:
        images.ensure(image)
    assert "docker build exited 1" in str(first.value) and not first.value.hung
    assert len(builds(fake_docker)) == 2
    with pytest.raises(images.ImageBuildError) as later:
        images.ensure(image)
    assert len(builds(fake_docker)) == 2, "the next test that needs it does not build again"
    assert "failed to build earlier in this session" in str(later.value)
    assert len(str(later.value).splitlines()) == 1
