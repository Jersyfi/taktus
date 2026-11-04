"""The image workflow publishes on a version tag and on `main` only, pushes only where a
registry is named, scans every image before it carries a tag, signs it without a key, records
its digest, and never deploys (issue #64, issue #347; ADR-0173; ADR-0013 D: Taktus does not put
itself into production)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from images import connector_names

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "images.yml"
SCANNER_CONFIG = ROOT / "deploy" / "images" / "grype.yaml"
DEPLOYING = re.compile(r"\b(helm|kubectl|kustomize|kubeconfig|ssh|scp)\b", re.IGNORECASE)
ENABLED = "needs.registry.outputs.enabled == 'true'"


def workflow() -> dict[str, Any]:
    document: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads the key `on` as true.
    document["on"] = document.pop(True, document.get("on"))
    return document


def steps(job: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = workflow()["jobs"][job]["steps"]
    return found


def step(job: str, name: str) -> dict[str, Any]:
    [found] = [s for s in steps(job) if s.get("name") == name or s.get("id") == name]
    return found


def position(job: str, name: str) -> int:
    return next(i for i, s in enumerate(steps(job)) if s.get("name") == name or s.get("id") == name)


def test_it_runs_on_a_version_tag_and_on_main_and_on_nothing_else() -> None:
    triggers = workflow()["on"]
    assert list(triggers) == ["push"], triggers
    assert triggers["push"] == {"tags": ["v*"], "branches": ["main"]}, triggers["push"]


def test_a_newer_push_to_main_cancels_the_older_build_and_a_tag_is_never_cancelled() -> None:
    concurrency = workflow()["concurrency"]
    assert concurrency["group"] == "images-${{ github.ref }}"
    assert concurrency["cancel-in-progress"] == "${{ github.ref == 'refs/heads/main' }}"


def test_main_is_tagged_with_its_commit_and_a_tag_with_its_version() -> None:
    check = workflow()["jobs"]["registry"]["steps"][0]
    assert check["env"]["COMMIT"] == "${{ github.sha }}"
    assert 'if [ "$REF" = "refs/heads/main" ]; then\n  tag="$COMMIT"' in check["run"]
    assert 'tag="${TAG#v}"' in check["run"]


def test_nothing_is_built_or_pushed_without_the_registry_variable() -> None:
    jobs = workflow()["jobs"]
    check = jobs["registry"]["steps"][0]
    assert check["env"]["REGISTRY"] == "${{ vars.IMAGE_REGISTRY }}"
    assert 'if [ -z "$REGISTRY" ]' in check["run"]
    assert jobs["build"]["if"] == ENABLED
    assert jobs["record"]["if"] == "${{ !cancelled() && " + ENABLED + " }}"
    # The proof publishes nothing, so it needs no registry.
    assert "if" not in jobs["proof"]
    assert "packages" not in jobs["proof"].get("permissions", {})


def test_it_has_no_deploy_step() -> None:
    for name, job in workflow()["jobs"].items():
        assert "environment" not in job, f"{name}: an environment is where a deployment goes"
        for each in job["steps"]:
            assert not DEPLOYING.search(each.get("run", "")), f"{name}: {each}"
            uses = each.get("uses", "")
            assert not re.search(r"deploy|k8s|helm|kube", uses, re.IGNORECASE), f"{name}: {uses}"


def test_the_control_plane_the_backup_and_each_worker_get_an_image() -> None:
    build = workflow()["jobs"]["build"]
    dockerfiles = {entry["dockerfile"] for entry in build["strategy"]["matrix"]["include"]}
    shipped = {str(p.relative_to(ROOT)) for p in (ROOT / "workers").glob("*/Dockerfile")}
    assert dockerfiles == {
        "deploy/docker/Dockerfile",
        "deploy/backup/Dockerfile",
        "connectors/Dockerfile",
        *shipped,
    }


def test_each_connector_gets_an_image_of_its_own_named_as_the_chart_pulls_it() -> None:
    """Every connector under connectors/ is released as its own image, its stage of
    connectors/Dockerfile, named `taktus-connector-<name>` (ADR-0158, issue #339)."""
    build = workflow()["jobs"]["build"]
    imaged = [e for e in build["strategy"]["matrix"]["include"] if "target" in e]
    assert {e["dockerfile"] for e in imaged} == {"connectors/Dockerfile"}
    assert {e["target"]: e["name"] for e in imaged} == {
        name: f"taktus-connector-{name}" for name in connector_names()
    }
    assert step("build", "build")["with"]["target"] == "${{ matrix.target }}"


def test_an_image_is_pushed_by_its_digest_alone_and_tagged_only_after_its_scan() -> None:
    """ADR-0173 §2: an image that fails its scan carries no tag and no signature."""
    build = step("build", "build")["with"]
    assert "tags" not in build, "a tag before the scan names an image nobody scanned"
    assert build["outputs"] == (
        "type=image,name=${{ env.IMAGE }},push-by-digest=true,name-canonical=true,push=true"
    )
    assert build["pull"] is True, "a fix published in the base image reaches the next build"
    env = workflow()["jobs"]["build"]["env"]
    assert env["IMAGE"] == "${{ vars.IMAGE_REGISTRY }}/${{ matrix.name }}"
    assert env["TAG"] == "${{ needs.registry.outputs.tag }}"
    assert "latest" not in str(env)
    for name in ("scan", "tag", "sign", "record"):
        assert step("build", name)["env"]["DIGEST"] == "${{ steps.build.outputs.digest }}"
    assert step("build", "scan")["run"] == 'tools/scan_image.sh "$IMAGE@$DIGEST" "$PLATFORMS"'
    assert step("build", "tag")["run"] == (
        'docker buildx imagetools create --tag "$IMAGE:$TAG" "$IMAGE@$DIGEST"'
    )
    order = [position("build", n) for n in ("build", "scan", "tag", "sign", "record")]
    assert order == sorted(order), "build, scan, tag, sign, record: in that order"


def test_the_scan_and_the_signature_use_the_pinned_tools_and_no_third_party_action() -> None:
    for job in ("proof", "build"):
        runs = [s.get("run", "") for s in steps(job)]
        assert "tools/install_image_tools.sh" in runs, job
        uses = [s.get("uses", "") for s in steps(job)]
        assert not [u for u in uses if re.search(r"grype|anchore|trivy|cosign|sigstore", u)]


def test_the_signature_is_keyless_through_the_workflows_own_identity() -> None:
    """ADR-0173 §5: no key, no secret; the build job alone may ask for an identity token."""
    sign = step("build", "sign")
    assert sign["run"] == '.tools/bin/cosign sign --yes "$IMAGE@$DIGEST"'
    assert "--key" not in sign["run"]
    assert set(sign["env"]) == {"DIGEST"}
    jobs = workflow()["jobs"]
    assert jobs["build"]["permissions"]["id-token"] == "write"
    for name, job in jobs.items():
        if name != "build":
            assert "id-token" not in job.get("permissions", {}), name
    assert workflow()["permissions"] == {"contents": "read"}
    text = WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"COSIGN_(KEY|PASSWORD|PRIVATE)", text)


def test_a_known_vulnerable_image_must_fail_the_scan_before_anything_is_built() -> None:
    """ADR-0173 §4: the proof runs first, publishes nothing, and passes only on findings."""
    document = workflow()
    assert document["jobs"]["build"]["needs"] == ["registry", "proof"]
    proof = document["jobs"]["proof"]["steps"]
    assert proof[-1]["run"] == 'tools/scan_image.sh --expect-findings "$PROOF_IMAGE"'
    image = document["env"]["PROOF_IMAGE"]
    assert re.fullmatch(r"alpine:3\.10\.0@sha256:[0-9a-f]{64}", image), "pinned by its digest"


def test_the_digests_are_recorded_with_the_charts_values() -> None:
    record = step("build", "record")
    assert set(record["env"]) == {"NAME", "DIGEST"}
    runs = " ".join(s.get("run", "") for s in steps("record"))
    assert "python3 tools/image_digests.py --in digests --out images" in runs
    assert "GITHUB_STEP_SUMMARY" in runs
    assert workflow()["jobs"]["record"]["needs"] == ["registry", "build"]


def test_every_exception_to_the_scan_names_its_vulnerability_and_a_reason() -> None:
    """ADR-0173 §3: a finding set aside is written down, with why."""
    config = yaml.safe_load(SCANNER_CONFIG.read_text(encoding="utf-8"))
    assert isinstance(config["ignore"], list)
    for entry in config["ignore"]:
        assert re.fullmatch(r"(CVE|GHSA|GO)-[0-9A-Za-z-]+", str(entry.get("vulnerability", "")))
        assert re.search(r"NTC-\d{4}", str(entry.get("reason", ""))), entry
    assert config["db"]["validate-age"] is True


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
    push = step("build", "build")
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


# --- the second coding worker's agent, pinned the same way (#208) -------------------------------

SECOND_AGENT_VERSION = ROOT / "workers" / "codex" / "agent-version"
SECOND_DOCKERFILE = ROOT / "workers" / "codex" / "Dockerfile"
SECOND_AGENT_PACKAGE = "@openai/codex"


def test_the_second_agents_version_is_one_exact_version() -> None:
    version = SECOND_AGENT_VERSION.read_text(encoding="utf-8").strip()
    assert EXACT.fullmatch(version), f"{SECOND_AGENT_VERSION.name} names {version!r}"


def test_the_second_coding_image_installs_the_pinned_version_and_nothing_else() -> None:
    text = SECOND_DOCKERFILE.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "COPY workers/codex/agent-version" in code
    assert not re.search(r"^\s*ARG\b", code, re.MULTILINE), "the agent's version is no argument"
    assert "latest" not in code
    installs = re.findall(rf"{re.escape(SECOND_AGENT_PACKAGE)}@(\S+?)\"", code)
    assert installs == ["${version}"], installs
    assert '"$(cat /tmp/agent-version)"' in code
    assert "grep -Eqx '[0-9]+\\.[0-9]+\\.[0-9]+'" in code
    # Nothing of the first coding worker: removing one must not touch the other.
    assert "claudecode" not in code


def test_the_release_builds_the_second_coding_image() -> None:
    build = workflow()["jobs"]["build"]
    second = [e for e in build["strategy"]["matrix"]["include"] if "codex" in e["dockerfile"]]
    assert [e["name"] for e in second] == ["taktus-worker-codex"]
