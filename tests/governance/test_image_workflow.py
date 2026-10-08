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
