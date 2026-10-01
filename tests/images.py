"""The images the tests build: built only when their content changed, and a hang says where.

Every image a test needs is built through `ensure`. It computes a digest of the Dockerfile and
of every file the Dockerfile copies from its context, labels the image with it, and tags it with
its first twelve characters as well as with its plain tag (`taktus:test-4754d2516c29` and
`taktus:test`). When the content tag exists and carries that label, `docker build` is not
invoked at all: a rerun touches neither the builder nor a registry. A newer base image upstream
is therefore not taken until the content changes or `make images REBUILD=1` asks for it.

The tests run the content tag, never the plain one. Several checkouts share one engine; one of
them building its own content under `taktus:test` moves that tag, and the image it moved away
from loses its last name and may be collected. The content tag keeps every content's image
named and apart. Tags of content no longer used stay on the engine until a person removes them.

When a build is needed, it runs with plain progress into a log file. A build that exceeds its
time, or prints nothing for `STALL_SECONDS`, is stopped, and the error names the image, the
steps that had started and not finished, the last lines, the elapsed time and the log. A build
that failed once in a session is not tried again by the next test that needs it: that test
fails with one line pointing at the first report.

Why: on 2026-09-29 two builds that take 1 and 14 seconds cold hung for 600 and 900 seconds in
one `make gates`, 25 of its 26 minutes, and `docker build -q` had discarded the output that
would have said where.

Runs as a script too — `make images` — to build ahead of the tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "org.taktus.test.content-digest"
LOG_DIR = ROOT / ".pytest_cache" / "taktus-images"
# A build that prints nothing for this long has stopped moving. Plain progress prints a line per
# step and per download update; no step of these Dockerfiles is silent for this long.
STALL_SECONDS = 120.0
INSPECT_SECONDS = 30.0


@dataclass(frozen=True)
class Image:
    tag: str
    dockerfile: Path
    context: Path
    # The whole build, bounded. The values are the ones the fixtures had before; they are not
    # raised — a build that needs them has hung, and the stall check says so sooner.
    timeout: float = 600.0
    stall: float = STALL_SECONDS


REFERENCE_WORKER = Image("taktus-worker-script:test", ROOT / "workers/script/Dockerfile", ROOT)
CONTROL_PLANE = Image("taktus:test", ROOT / "deploy/docker/Dockerfile", ROOT, timeout=900.0)
HOG_CONTEXT = ROOT / "tests/adapters/execution/hog"
HOG = Image("taktus-test-unit:hog", HOG_CONTEXT / "Dockerfile", HOG_CONTEXT)
ALL = (REFERENCE_WORKER, CONTROL_PLANE, HOG)


class ImageBuildError(Exception):
    """An image the tests need could not be built; the message says where and why. `hung` is
    true for a build that was stopped — timed out or stalled — rather than one that failed."""

    def __init__(self, message: str, *, log: Path | None = None, hung: bool = False) -> None:
        super().__init__(message)
        self.log = log
        self.hung = hung


# --- the content digest -----------------------------------------------------------------------


def _instructions(dockerfile: str) -> list[str]:
    """The Dockerfile's instructions, continuation lines joined, comments dropped."""
    lines: list[str] = []
    current = ""
    for raw in dockerfile.splitlines():
        stripped = raw.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        current += stripped
        lines.append(current)
        current = ""
    if current:
        lines.append(current)
    return lines


def copied_sources(dockerfile: str) -> list[str]:
    """Every context path a COPY or ADD instruction reads; `--from=` copies read a stage."""
    sources: list[str] = []
    for instruction in _instructions(dockerfile):
        keyword, _, rest = instruction.partition(" ")
        if keyword.upper() not in ("COPY", "ADD"):
            continue
        rest = rest.strip()
        if rest.startswith("["):
            words = [str(word) for word in json.loads(rest)]
            flags: list[str] = []
        else:
            words = shlex.split(rest)
            flags = [word for word in words if word.startswith("--")]
            words = [word for word in words if not word.startswith("--")]
        if any(flag.startswith("--from=") for flag in flags):
            continue
        sources.extend(words[:-1])
    return sources


def _pattern(pattern: str) -> re.Pattern[str]:
    """A .dockerignore pattern as a regular expression on a context-relative path."""
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            if pattern.startswith("/", i):
                out = out[:-2] + "(?:.*/)?"
                i += 1
            continue
        char = pattern[i]
        out += "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char)
        i += 1
    return re.compile(out)


def _ignore_rules(context: Path) -> list[tuple[bool, re.Pattern[str]]]:
    path = context / ".dockerignore"
    if not path.is_file():
        return []
    rules: list[tuple[bool, re.Pattern[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        line = line.removeprefix("!").strip().strip("/")
        rules.append((negate, _pattern(os.path.normpath(line))))
    return rules


def _ignored(relative: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """Docker's rule: the last matching pattern wins, and a pattern that matches a directory
    matches everything under it."""
    parts = relative.split("/")
    prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    ignored = False
    for negate, rule in rules:
        if any(rule.fullmatch(prefix) for prefix in prefixes):
            ignored = not negate
    return ignored


def content_digest(image: Image) -> str:
    """sha256 over the Dockerfile and every copied file: its context path, its executable bit
    and its bytes, in a stable order."""
    text = image.dockerfile.read_text(encoding="utf-8")
    rules = _ignore_rules(image.context)
    files: set[Path] = set()
    for source in copied_sources(text):
        if "://" in source:
            continue  # a URL is in the Dockerfile's text, which is hashed
        for match in sorted(image.context.glob(source)) or [image.context / source]:
            if match.is_dir():
                files.update(p for p in match.rglob("*") if p.is_file())
            elif match.is_file():
                files.add(match)
            else:
                raise ImageBuildError(f"{image.tag}: {image.dockerfile} copies {source}, absent")
    digest = hashlib.sha256()
    digest.update(text.encode())
    for path in sorted(files):
        relative = path.relative_to(image.context).as_posix()
        if _ignored(relative, rules):
            continue
        executable = b"x" if os.access(path, os.X_OK) else b"-"
        digest.update(b"\0" + relative.encode() + b"\0" + executable)
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


# --- the engine -------------------------------------------------------------------------------


def present(tag: str) -> str | None:
    """The content label of the image with this tag; None when there is no such image or it
    carries no label."""
    # `.Config`, not `.Config.Labels`: the template fails on an image that has no labels at all.
    command = ["docker", "image", "inspect", "--format", "{{json .Config}}", tag]
    try:
        completed = subprocess.run(  # noqa: S603 — fixed arguments
            command,
            capture_output=True,
            text=True,
            timeout=INSPECT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ImageBuildError(
            f"{tag}: the engine did not answer `docker image inspect` within "
            f"{INSPECT_SECONDS:.0f} s — the engine itself is stuck, not the build"
        ) from error
    if completed.returncode != 0:
        return None
    config = json.loads(completed.stdout or "null") or {}
    value = (config.get("Labels") or {}).get(LABEL)
    return str(value) if value else None


def content_tag(image: Image, digest: str) -> str:
    """The tag that names this content: the plain tag with the digest's first characters."""
    return f"{image.tag}-{digest[:12]}"


_STEP = re.compile(r"^#(\d+) (.*)$")
_END = re.compile(r"^(DONE|CACHED|ERROR|CANCELED)\b")


def unfinished_steps(log: str) -> list[str]:
    """The build steps plain progress shows as started and not finished, in order."""
    started: dict[str, str] = {}
    finished: set[str] = set()
    for line in log.splitlines():
        match = _STEP.match(line.strip())
        if match is None:
            continue
        number, rest = match.groups()
        if _END.match(rest):
            finished.add(number)
        elif rest.startswith("[") and number not in started:
            started[number] = f"#{number} {rest}"
    return [text for number, text in started.items() if number not in finished]


def _diagnosis(
    image: Image, what: str, log_path: Path, elapsed: float, *, hung: bool
) -> ImageBuildError:
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    steps = unfinished_steps(log)
    tail = [line for line in log.splitlines() if line.strip()][-8:]
    lines = [
        f"the test image {image.tag} did not build: {what}, after {elapsed:.0f} s",
        f"  Dockerfile: {image.dockerfile}",
        "  steps started and not finished: " + ("; ".join(steps) if steps else "none shown"),
        "  last lines of the build:",
        *(f"    {line}" for line in tail or ["(the build printed nothing)"]),
        f"  full log: {log_path}",
    ]
    return ImageBuildError("\n".join(lines), log=log_path, hung=hung)


def build(image: Image, digest: str) -> str:
    """Build the image with its content label and both tags; the content tag. Raises
    ImageBuildError naming where a failed, timed-out or stalled build stopped."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "-", image.tag) + ".log")
    tag = content_tag(image, digest)
    command = [
        "docker",
        "build",
        "--progress=plain",
        "--label",
        f"{LABEL}={digest}",
        "-f",
        str(image.dockerfile),
        "-t",
        tag,
        "-t",
        image.tag,
        str(image.context),
    ]
    started = time.monotonic()
    with log_path.open("wb") as log:
        log.write(f"$ {shlex.join(command)}\n".encode())
        log.flush()
        process = subprocess.Popen(  # noqa: S603 — our own Dockerfiles, fixed arguments
            command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
        )
        size, moved = log_path.stat().st_size, started
        stopped: str | None = None
        while process.poll() is None:
            time.sleep(0.1)
            now = time.monotonic()
            if (current := log_path.stat().st_size) != size:
                size, moved = current, now
            if now - started > image.timeout:
                stopped = f"timed out at its bound of {image.timeout:g} s"
            elif now - moved > image.stall:
                stopped = f"stalled — no output for {image.stall:g} s"
            if stopped is not None:
                process.kill()
                process.wait()
                break
    elapsed = time.monotonic() - started
    if stopped is not None:
        raise _diagnosis(image, stopped, log_path, elapsed, hung=True)
    if process.returncode != 0:
        what = f"docker build exited {process.returncode}"
        raise _diagnosis(image, what, log_path, elapsed, hung=False)
    return tag


# --- once per session -------------------------------------------------------------------------


@dataclass
class _Session:
    ready: dict[str, str] = field(default_factory=dict)
    built: set[str] = field(default_factory=set)
    failed: dict[str, Path | None] = field(default_factory=dict)


_session = _Session()


def ensure(image: Image, *, rebuild: bool = False) -> str:
    """The content tag of the image, built first only when its content changed. A failure is
    reported in full once; every later call in the same process fails with one line pointing
    at it."""
    if image.tag in _session.ready and not rebuild:
        return _session.ready[image.tag]
    if image.tag in _session.failed:
        raise ImageBuildError(
            f"the test image {image.tag} failed to build earlier in this session; the first "
            f"test that needed it reports why (log: {_session.failed[image.tag]})"
        )
    try:
        digest = content_digest(image)
        identifier = content_tag(image, digest)
        if rebuild or present(identifier) != digest:
            attempts = 2  # one transient failure — a registry that answered 5xx — is retried
            for attempt in range(1, attempts + 1):
                try:
                    identifier = build(image, digest)
                    _session.built.add(image.tag)
                    break
                except ImageBuildError as error:
                    # A hang is never retried: it would double the cost of the same answer.
                    if error.hung or attempt == attempts:
                        raise
    except ImageBuildError as error:
        _session.failed[image.tag] = error.log
        raise
    _session.ready[image.tag] = identifier
    return identifier


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build the test images whose content changed.")
    parser.add_argument("--rebuild", action="store_true", help="build even when the label fits")
    arguments = parser.parse_args(argv)
    code = 0
    for image in ALL:
        started = time.monotonic()
        try:
            tag = ensure(image, rebuild=arguments.rebuild)
        except ImageBuildError as error:
            print(error)
            code = 1
            continue
        state = "built" if image.tag in _session.built else "unchanged, not built"
        print(f"image {tag}: {state}, {time.monotonic() - started:.1f}s")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
