"""The image workflow builds on a version tag only, pushes only where a registry is named, and
never deploys (issue #64; ADR-0013 D: Taktus does not put itself into production)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "images.yml"
DEPLOYING = re.compile(r"\b(helm|kubectl|kustomize|kubeconfig|ssh|scp)\b", re.IGNORECASE)


def workflow() -> dict[str, Any]:
    document: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as true.
    document["on"] = document.pop(True, document.get("on"))
    return document


def test_it_runs_on_a_tag_and_on_nothing_else() -> None:
    triggers = workflow()["on"]
    assert list(triggers) == ["push"], triggers
    assert set(triggers["push"]) == {"tags"}, triggers["push"]


def test_nothing_is_built_or_pushed_without_the_registry_variable() -> None:
    jobs = workflow()["jobs"]
    check = jobs["registry"]["steps"][0]
    assert check["env"]["REGISTRY"] == "${{ vars.IMAGE_REGISTRY }}"
    assert 'if [ -z "$REGISTRY" ]' in check["run"]
    for name, job in jobs.items():
        if name != "registry":
            assert job["if"] == "needs.registry.outputs.enabled == 'true'", name


def test_it_has_no_deploy_step() -> None:
    for name, job in workflow()["jobs"].items():
        assert "environment" not in job, f"{name}: an environment is where a deployment goes"
        for step in job["steps"]:
            assert not DEPLOYING.search(step.get("run", "")), f"{name}: {step}"
            uses = step.get("uses", "")
            assert not re.search(r"deploy|k8s|helm|kube", uses, re.IGNORECASE), f"{name}: {uses}"


def test_the_control_plane_and_every_shipped_worker_get_an_image_tagged_with_the_version() -> None:
    build = workflow()["jobs"]["build"]
    dockerfiles = {entry["dockerfile"] for entry in build["strategy"]["matrix"]["include"]}
    shipped = {str(p.relative_to(ROOT)) for p in (ROOT / "workers").glob("*/Dockerfile")}
    assert dockerfiles == {"deploy/docker/Dockerfile", *shipped}
    push = next(s for s in build["steps"] if s.get("uses", "").startswith("docker/build-push"))
    assert push["with"]["tags"].endswith(":${{ needs.registry.outputs.version }}")
    assert "latest" not in push["with"]["tags"]


# --- the coding worker's agent, pinned (#116) ---------------------------------------------------

AGENT_VERSION = ROOT / "workers" / "claudecode" / "agent-version"
CODING_DOCKERFILE = ROOT / "workers" / "claudecode" / "Dockerfile"
LIVE = ROOT / ".github" / "workflows" / "live.yml"
EXACT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
AGENT_PACKAGE = "@anthropic-ai/claude-code"


def test_the_agents_version_is_one_exact_version() -> None:
    """Not `latest`, not a dist-tag, not a range: two builds of one tag carry the same agent."""
    version = AGENT_VERSION.read_text(encoding="utf-8").strip()
    assert EXACT.fullmatch(version), f"{AGENT_VERSION.name} names {version!r}, not one version"


def test_the_coding_image_installs_the_pinned_version_and_nothing_else() -> None:
    text = CODING_DOCKERFILE.read_text(encoding="utf-8")
    instructions = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    code = "\n".join(instructions)
    assert "COPY workers/claudecode/agent-version" in code
    # A build argument would let a release build install another version than the file's.
    assert not re.search(r"^\s*ARG\b", code, re.MULTILINE), "the agent's version is no argument"
    assert "latest" not in code
    installs = re.findall(rf"{re.escape(AGENT_PACKAGE)}@(\S+?)\"", code)
    assert installs == ["${version}"], installs
    assert '"$(cat /tmp/agent-version)"' in code
    # The build refuses a file that does not name an exact version.
    assert "grep -Eqx '[0-9]+\\.[0-9]+\\.[0-9]+'" in code


def test_the_release_build_passes_no_other_agent_version() -> None:
    build = workflow()["jobs"]["build"]
    coding = [e for e in build["strategy"]["matrix"]["include"] if "claudecode" in e["dockerfile"]]
    assert coding, "the coding worker's image is built on a release"
    push = next(s for s in build["steps"] if s.get("uses", "").startswith("docker/build-push"))
    assert push["with"]["context"] == ".", "the build context holds the version file"
    assert "build-args" not in push["with"], "a build argument would override the pin"


def test_the_live_test_installs_the_version_the_image_carries() -> None:
    """The live job proves what ships: it installs the agent from the same file (#116)."""
    document: dict[Any, Any] = yaml.safe_load(LIVE.read_text(encoding="utf-8"))
    runs = [str(step.get("run", "")) for step in document["jobs"]["coding"]["steps"]]
    installs = [r for r in runs if "npm install" in r]
    assert len(installs) == 1, installs
    assert 'pinned="$(cat workers/claudecode/agent-version)"' in installs[0]
    install = [line for line in installs[0].splitlines() if "npm install" in line]
    assert install == [f'npm install --global "{AGENT_PACKAGE}@${{pinned}}"'], install
