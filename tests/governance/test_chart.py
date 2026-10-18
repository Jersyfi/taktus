"""The chart renders least privilege, or the gate fails (deploy/k8s/README.md, issue #64).

`helm lint` and `helm template` run against `deploy/k8s/values.example.yaml`, and the rendered
manifests are read back: what the deployment identity may install, the admission labels, the
default-deny policies, Taktus's Role, the jobs' account, secrets as files only, and versions as
image tags. Without helm these tests skip and say so; CI installs the pinned helm (`make helm`)
and sets `TAKTUS_REQUIRE_HELM`, under which a missing helm fails instead: a gate that goes
green because it could not look is broken (DEC-0004).

The values files are read without helm: none may carry a secret value, a hostname or an address.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.adapters.driven.execution.kubernetes.api import PERMITTED

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "k8s" / "chart"
EXAMPLE = ROOT / "deploy" / "k8s" / "values.example.yaml"
RELEASE_NAMESPACE = "taktus"
EXECUTION_NAMESPACE = "taktus-execution"

# What the deployment identity may create and change in the two namespaces (NEED-0007). The
# chart renders nothing else: no cluster-wide object, no certificate, no disruption budget.
ALLOWED_KINDS = {
    "Secret",
    "ConfigMap",
    "Service",
    "ServiceAccount",
    "PersistentVolumeClaim",
    "Deployment",
    "StatefulSet",
    "Job",
    "CronJob",
    "Role",
    "RoleBinding",
    "NetworkPolicy",
    "Ingress",
}
VERSION_TAG = re.compile(r"^v?\d+(\.\d+)*([-+._][0-9A-Za-z.-]+)?$")


def helm() -> str:
    for candidate in (os.environ.get("TAKTUS_HELM"), str(ROOT / ".tools" / "bin" / "helm")):
        if candidate and Path(candidate).is_file():
            return candidate
    found = shutil.which("helm")
    if found:
        return found
    message = "the chart tests need helm: `make helm` installs the pinned version into .tools/bin"
    if os.environ.get("TAKTUS_REQUIRE_HELM"):
        pytest.fail(message + " — and TAKTUS_REQUIRE_HELM says they may not skip")
    pytest.skip(message)


def run_helm(*args: str) -> subprocess.CompletedProcess[str]:
    # A fixed executable and arguments assembled in this file: nothing untrusted.
    return subprocess.run(  # noqa: S603
        [helm(), *args], capture_output=True, text=True, timeout=120, check=False
    )


def render(*sets: str, example: bool = True) -> list[dict[str, Any]]:
    args = ["template", "taktus", str(CHART), "--namespace", RELEASE_NAMESPACE]
    if example:
        args += ["-f", str(EXAMPLE)]
    for item in sets:
        args += ["--set", item]
    completed = run_helm(*args)
    assert completed.returncode == 0, completed.stderr
    return [d for d in yaml.safe_load_all(completed.stdout) if d]


def render_fails(*sets: str) -> str:
    args = ["template", "taktus", str(CHART), "--namespace", RELEASE_NAMESPACE, "-f", str(EXAMPLE)]
    for item in sets:
        args += ["--set", item]
    completed = run_helm(*args)
    assert completed.returncode != 0, "the chart rendered what it must refuse"
    return completed.stderr


def of_kind(documents: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [d for d in documents if d["kind"] == kind]


def pod_specs(documents: list[dict[str, Any]]) -> Iterator[tuple[str, dict[str, Any]]]:
    for document in documents:
        if document["kind"] in ("Deployment", "StatefulSet", "Job"):
            yield document["metadata"]["name"], document["spec"]["template"]["spec"]
        elif document["kind"] == "CronJob":
            template = document["spec"]["jobTemplate"]["spec"]["template"]
            yield document["metadata"]["name"], template["spec"]


def containers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [*spec.get("initContainers", []), *spec["containers"]]


@pytest.fixture(scope="module")
def rendered() -> list[dict[str, Any]]:
    return render()


def test_helm_lint_passes_with_the_example_values() -> None:
    completed = run_helm(
        "lint", str(CHART), "--strict", "--namespace", RELEASE_NAMESPACE, "-f", str(EXAMPLE)
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_every_kind_is_one_the_deployment_identity_may_manage(
    rendered: list[dict[str, Any]],
) -> None:
    kinds = {d["kind"] for d in rendered}
    assert kinds <= ALLOWED_KINDS, (
        f"outside the deployment identity's rights: {kinds - ALLOWED_KINDS}"
    )
    namespaces = {d["metadata"].get("namespace") for d in rendered}
    assert namespaces == {RELEASE_NAMESPACE, EXECUTION_NAMESPACE}


def test_ingress_on_renders_nothing_outside_the_list() -> None:
    documents = render(
        "ingress.host=example",
        "ingress.tls.issuer=issuer",
        "networkPolicy.apiServer.cidrs={10.0.0.0/8}",
    )
    assert {d["kind"] for d in documents} <= ALLOWED_KINDS


def test_no_namespace_is_rendered_unless_asked(rendered: list[dict[str, Any]]) -> None:
    assert of_kind(rendered, "Namespace") == []


def test_the_execution_namespace_carries_the_restricted_admission_labels() -> None:
    namespaces = {
        d["metadata"]["name"]: d["metadata"]["labels"]
        for d in of_kind(render("namespaces.create=true"), "Namespace")
    }
    labels = namespaces[EXECUTION_NAMESPACE]
    for mode in ("enforce", "audit", "warn"):
        assert labels[f"pod-security.kubernetes.io/{mode}"] == "restricted"


def test_every_pod_satisfies_the_restricted_profile(rendered: list[dict[str, Any]]) -> None:
    for name, spec in pod_specs(rendered):
        assert spec["securityContext"]["runAsNonRoot"] is True, name
        assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault", name
        for container in containers(spec):
            context = container["securityContext"]
            assert context["allowPrivilegeEscalation"] is False, name
            assert context["capabilities"]["drop"] == ["ALL"], name
            assert context["readOnlyRootFilesystem"] is True, name


def test_a_default_deny_policy_with_both_types_exists_in_both_namespaces(
    rendered: list[dict[str, Any]],
) -> None:
    deny = {
        d["metadata"]["namespace"]
        for d in of_kind(rendered, "NetworkPolicy")
        if d["spec"]["podSelector"] == {}
        and set(d["spec"]["policyTypes"]) == {"Ingress", "Egress"}
        and not d["spec"].get("ingress")
        and not d["spec"].get("egress")
    }
    assert deny == {RELEASE_NAMESPACE, EXECUTION_NAMESPACE}


def test_a_unit_reaches_the_egress_proxy_and_nothing_else(rendered: list[dict[str, Any]]) -> None:
    unit = next(
        d
        for d in of_kind(rendered, "NetworkPolicy")
        if d["spec"]["podSelector"].get("matchLabels") == {"taktus/role": "unit"}
    )
    assert unit["metadata"]["namespace"] == EXECUTION_NAMESPACE
    [egress] = unit["spec"]["egress"]
    assert egress["to"] == [{"podSelector": {"matchLabels": {"taktus/role": "egress"}}}]
    [ingress] = unit["spec"]["ingress"]
    [peer] = ingress["from"]
    assert peer["namespaceSelector"]["matchLabels"] == {
        "kubernetes.io/metadata.name": RELEASE_NAMESPACE
    }


def test_taktus_holds_a_role_never_a_cluster_role_exactly_as_the_plan_states_it(
    rendered: list[dict[str, Any]],
) -> None:
    kinds = {d["kind"] for d in rendered}
    assert "ClusterRole" not in kinds and "ClusterRoleBinding" not in kinds
    [role] = of_kind(rendered, "Role")
    assert role["metadata"]["namespace"] == EXECUTION_NAMESPACE
    granted = {
        (group, resource): set(rule["verbs"])
        for rule in role["rules"]
        for group in rule["apiGroups"]
        for resource in rule["resources"]
    }
    assert granted == {
        ("batch", "jobs"): {"create", "get", "list", "watch", "delete"},
        ("", "pods"): {"get", "list"},
        ("", "pods/log"): {"get", "list"},
        ("", "secrets"): {"create", "delete"},
        ("", "services"): {"create", "delete"},
    }
    # Every call the cluster adapter's client permits itself is one the Role grants.
    for resource, verb in PERMITTED:
        group = "batch" if resource == "jobs" else ""
        assert verb in granted[(group, resource)], (resource, verb)
    [binding] = of_kind(rendered, "RoleBinding")
    assert binding["metadata"]["namespace"] == EXECUTION_NAMESPACE
    assert binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": role["metadata"]["name"],
    }
    [subject] = binding["subjects"]
    assert subject["kind"] == "ServiceAccount"
    assert subject["namespace"] == RELEASE_NAMESPACE


def test_the_job_account_and_every_pod_but_the_runner_carry_no_token(
    rendered: list[dict[str, Any]],
) -> None:
    accounts = {d["metadata"]["namespace"]: d for d in of_kind(rendered, "ServiceAccount")}
    assert accounts[EXECUTION_NAMESPACE]["automountServiceAccountToken"] is False
    assert accounts[RELEASE_NAMESPACE]["automountServiceAccountToken"] is False
    with_token = {
        name for name, spec in pod_specs(rendered) if spec["automountServiceAccountToken"]
    }
    assert with_token == {"taktus-runner"}


def test_every_secret_is_a_mounted_file_and_never_an_environment_variable() -> None:
    documents = render(
        "telemetry.otlp.endpoint=http://collector:4317",
        "telemetry.otlp.headersSecret=otlp",
        "telemetry.otlp.headersKey=headers",
    )
    variables = 0
    for name, spec in pod_specs(documents):
        secret_volumes = {v["name"] for v in spec.get("volumes", []) if "secret" in v}
        for container in containers(spec):
            for source in container.get("envFrom", []):
                assert "secretRef" not in source, f"{name}: a Secret as environment"
            mounts = {m["name"]: m["mountPath"] for m in container.get("volumeMounts", [])}
            secret_mounts = [path for volume, path in mounts.items() if volume in secret_volumes]
            assert set(secret_volumes) <= set(mounts), f"{name}: a Secret volume not mounted"
            for variable in container.get("env", []):
                assert "valueFrom" not in variable, f"{name}: {variable['name']} from a Secret"
                if variable["name"].endswith("_FILE"):
                    variables += 1
                    assert any(variable["value"].startswith(p + "/") for p in secret_mounts), (
                        f"{name}: {variable['name']} points at no mounted Secret"
                    )
    for config in of_kind(documents, "ConfigMap"):
        assert not [key for key in config["data"] if key.endswith("_FILE")]
    assert of_kind(documents, "Secret") == [], "the chart creates no Secret: it names existing ones"
    assert variables >= 8


def test_every_image_tag_is_a_version(rendered: list[dict[str, Any]]) -> None:
    images = [c["image"] for _, spec in pod_specs(rendered) for c in containers(spec)]
    [config] = of_kind(rendered, "ConfigMap")
    images += [
        config["data"]["TAKTUS_EXECUTION_UNIT"],
        config["data"]["TAKTUS_EXECUTION_EGRESS_IMAGE"],
    ]
    for image in images:
        repository, _, tag = image.rpartition(":")
        assert repository and "/" not in tag, f"{image} names no tag"
        assert VERSION_TAG.match(tag) and tag != "latest", f"{image}: not a version"


@pytest.mark.parametrize(
    "setting",
    [
        "image.tag=latest",
        "image.tag=",
        "database.image.tag=latest",
        "execution.image=worker:latest",
    ],
)
def test_a_tag_that_is_not_a_version_is_refused(setting: str) -> None:
    assert "tag" in render_fails(setting)


def test_one_deployment_per_role_and_migrations_with_the_same_image(
    rendered: list[dict[str, Any]],
) -> None:
    deployments = {
        d["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"]: d
        for d in of_kind(rendered, "Deployment")
        if d["metadata"]["labels"]["app.kubernetes.io/component"] == "control-plane"
    }
    assert set(deployments) == {"api", "runner", "scheduler", "automation"}
    [job] = of_kind(rendered, "Job")
    assert job["metadata"]["annotations"]["helm.sh/hook"] == "post-install,pre-upgrade"
    image = job["spec"]["template"]["spec"]["containers"][0]["image"]
    assert {
        d["spec"]["template"]["spec"]["containers"][0]["image"] for d in deployments.values()
    } == {image}
    external = of_kind(render("database.deploy=false"), "Job")[0]
    assert external["metadata"]["annotations"]["helm.sh/hook"] == "pre-install,pre-upgrade"


def test_the_database_is_its_own_with_a_twenty_gibibyte_volume_that_is_watched(
    rendered: list[dict[str, Any]],
) -> None:
    [database] = of_kind(rendered, "StatefulSet")
    [claim] = database["spec"]["volumeClaimTemplates"]
    assert claim["spec"]["resources"]["requests"]["storage"] == "20Gi"
    [config] = of_kind(rendered, "ConfigMap")
    assert config["data"]["TAKTUS_CAPACITY_DATABASE_VOLUME_MB"] == "20480"
    assert config["data"]["TAKTUS_CAPACITY_STORAGE_EXPANDABLE"] == "false"
    assert config["data"]["TAKTUS_MIGRATE_ON_START"] == "false"


def test_the_chat_connector_is_reached_by_the_roles_alone_and_reads_its_secrets_as_files(
    rendered: list[dict[str, Any]],
) -> None:
    """Issue #239: the chat channel's connector is deployed with the instance, from the
    control plane's image, with its bot token and signing secret as mounted files; it is
    reached from the roles alone and mounts no token. Disabled, nothing of it is rendered."""
    [connector] = [
        d
        for d in of_kind(rendered, "Deployment")
        if d["metadata"]["labels"]["app.kubernetes.io/component"] == "connector-chat"
    ]
    spec = connector["spec"]["template"]["spec"]
    assert spec["automountServiceAccountToken"] is False
    [container] = spec["containers"]
    assert container["command"][:3] == ["python", "-m", "taktus.adapters.driven.connectors.slack"]
    variables = {v["name"]: v["value"] for v in container["env"]}
    assert variables == {
        "TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE": "/run/secrets/taktus/chat/bot-token",
        "TAKTUS_CREDENTIAL_CHAT_SIGNING_SECRET_FILE": "/run/secrets/taktus/chat/signing-secret",
    }
    [policy] = [
        d
        for d in of_kind(rendered, "NetworkPolicy")
        if d["metadata"]["name"] == "taktus-connector-chat"
    ]
    [allowed] = policy["spec"]["ingress"]
    [peer] = allowed["from"]
    assert peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"] == "control-plane"
    off = render("connectors.chat.enabled=false")
    assert not [d for d in off if "connector-chat" in d["metadata"]["name"]]
    [config] = of_kind(off, "ConfigMap")
    assert "channel.chat" not in config["data"]["TAKTUS_CONNECTORS"]


def test_a_new_release_leaves_the_database_pod_as_it_is() -> None:
    """Issue #237: an upgrade that changes only the image tag does not change the database's
    pod template, so the StatefulSet does not replace its pod and the roles keep their
    database. A change of the database's own image does."""

    def database_template(*sets: str) -> dict[str, Any]:
        [database] = of_kind(render(*sets), "StatefulSet")
        template: dict[str, Any] = database["spec"]["template"]
        return template

    assert database_template("image.tag=0.2.0") == database_template("image.tag=0.3.0")
    assert database_template("database.image.tag=16-alpine") != database_template(
        "database.image.tag=17-alpine"
    )


def test_the_cluster_adapter_is_wired_to_the_namespace_the_account_and_the_state_claim() -> None:
    documents = render("execution.kind=cluster", "execution.stateClaim=unit-state")
    [config] = of_kind(documents, "ConfigMap")
    data = config["data"]
    assert data["TAKTUS_EXECUTION"] == "cluster"
    assert data["TAKTUS_EXECUTION_NAMESPACE"] == EXECUTION_NAMESPACE
    assert data["TAKTUS_EXECUTION_SERVICE_ACCOUNT"] == "taktus-unit"
    assert data["TAKTUS_EXECUTION_EGRESS_ENFORCE"] == "true"
    assert data["TAKTUS_EXECUTION_STATE_CLAIM"] == "unit-state"
    assert data["TAKTUS_EXECUTION_CPU_REQUEST_SHARE"] == "0.25", "a quarter of the CPU limit"
    claims = {
        (d["metadata"]["namespace"], d["metadata"]["name"])
        for d in of_kind(documents, "PersistentVolumeClaim")
    }
    assert (EXECUTION_NAMESPACE, "unit-state") in claims
    assert {d["kind"] for d in documents} <= ALLOWED_KINDS


def test_service_hosts_are_configuration_for_the_instance_and_each_worker() -> None:
    """ADR-0089: the hosts a worker's own service needs are rendered from the values, the
    instance's as the default and a worker's own where it names them — an empty list too."""
    [config] = of_kind(render("execution.kind=cluster"), "ConfigMap")
    assert config["data"]["TAKTUS_EXECUTION_SERVICE_HOSTS"] == "", "none unless configured"
    documents = render(
        "execution.kind=cluster",
        "execution.defaults.serviceHosts={model.example.net,10.0.0.7:8443}",
        "execution.workers[0].name=coding",
        "execution.workers[0].image=taktus-worker-coding:0.1.0",
        "execution.workers[0].serviceHosts={agent.example.net}",
        "execution.workers[1].name=plain",
        "execution.workers[1].image=taktus-worker-plain:0.1.0",
        "execution.workers[1].serviceHosts={}",
        "execution.workers[2].name=shared",
        "execution.workers[2].image=taktus-worker-shared:0.1.0",
    )
    [config] = of_kind(documents, "ConfigMap")
    data = config["data"]
    assert data["TAKTUS_EXECUTION_SERVICE_HOSTS"] == "model.example.net,10.0.0.7:8443"
    assert data["TAKTUS_WORKER_CODING_EXECUTION_SERVICE_HOSTS"] == "agent.example.net"
    assert data["TAKTUS_WORKER_PLAIN_EXECUTION_SERVICE_HOSTS"] == "", "its own: none"
    assert "TAKTUS_WORKER_SHARED_EXECUTION_SERVICE_HOSTS" not in data, "the instance's"


def test_a_units_variables_are_configuration_for_the_instance_and_each_worker() -> None:
    """ADR-0090: the variables a worker's unit is given are rendered from the values into the
    ConfigMap, the instance's as the default and a worker's own map where it names one — an
    empty map too. A value with a comma is refused: the comma separates the pairs."""
    [config] = of_kind(render("execution.kind=cluster"), "ConfigMap")
    assert config["data"]["TAKTUS_EXECUTION_UNIT_ENV"] == "", "none unless configured"
    documents = render(
        "execution.kind=cluster",
        "execution.defaults.unitEnv.LOG_FORMAT=json",
        "execution.workers[0].name=coding",
        "execution.workers[0].image=taktus-worker-coding:0.1.0",
        "execution.workers[0].unitEnv.CODING_AGENT_AUTH=api-key",
        "execution.workers[0].unitEnv.CODING_AGENT_MODEL=m-1",
        "execution.workers[1].name=plain",
        "execution.workers[1].image=taktus-worker-plain:0.1.0",
        "execution.workers[1].unitEnv=",
        "execution.workers[2].name=shared",
        "execution.workers[2].image=taktus-worker-shared:0.1.0",
    )
    [config] = of_kind(documents, "ConfigMap")
    data = config["data"]
    assert data["TAKTUS_EXECUTION_UNIT_ENV"] == "LOG_FORMAT=json"
    assert data["TAKTUS_WORKER_CODING_EXECUTION_UNIT_ENV"] == (
        "CODING_AGENT_AUTH=api-key,CODING_AGENT_MODEL=m-1"
    )
    assert data["TAKTUS_WORKER_PLAIN_EXECUTION_UNIT_ENV"] == "", "its own: none"
    assert "TAKTUS_WORKER_SHARED_EXECUTION_UNIT_ENV" not in data, "the instance's"
    refused = render_fails("execution.kind=cluster", "execution.defaults.unitEnv.A=x\\,y")
    assert "holds a comma" in refused


def test_several_workers_are_configuration_each_with_its_own_credentials() -> None:
    """Issue #209, ADR-0078: the chart names several workers in order, each with what it sets
    itself, and mounts a credential for one worker under that worker's parameter."""
    documents = render(
        "execution.kind=cluster",
        "execution.workers[0].name=coding",
        "execution.workers[0].image=taktus-worker-coding:0.1.0",
        "execution.workers[1].name=coding-second",
        "execution.workers[1].image=taktus-worker-coding-second:0.1.0",
        "execution.workers[1].memoryMb=2048",
        "execution.workers[1].cpuRequestShare=1",
        "execution.workers[2].name=shell",
        "execution.workers[2].kind=endpoint",
        "execution.workers[2].endpoint=http://shell:9000",
        "credentials[1].parameter=worker.coding-second.credential.coding_agent_api_key",
        "credentials[1].secret=taktus-coding-second",
        "credentials[1].key=api-key",
    )
    [config] = of_kind(documents, "ConfigMap")
    data = config["data"]
    assert data["TAKTUS_WORKERS"] == "coding,coding-second,shell"
    assert data["TAKTUS_WORKER_CODING_EXECUTION_UNIT"] == "taktus-worker-coding:0.1.0"
    assert data["TAKTUS_WORKER_CODING_SECOND_EXECUTION_UNIT"] == "taktus-worker-coding-second:0.1.0"
    assert data["TAKTUS_WORKER_CODING_SECOND_EXECUTION_MEMORY_MB"] == "2048"
    assert "TAKTUS_WORKER_CODING_EXECUTION_MEMORY_MB" not in data, "the instance's is the default"
    assert data["TAKTUS_WORKER_CODING_SECOND_EXECUTION_CPU_REQUEST_SHARE"] == "1"
    assert "TAKTUS_WORKER_CODING_EXECUTION_CPU_REQUEST_SHARE" not in data
    assert data["TAKTUS_WORKER_SHELL_EXECUTION"] == "endpoint"
    assert data["TAKTUS_WORKER_SHELL_ENDPOINT"] == "http://shell:9000"
    variables = {
        variable["name"]
        for _, spec in pod_specs(documents)
        for container in containers(spec)
        for variable in container.get("env", [])
    }
    assert "TAKTUS_WORKER_CODING_SECOND_CREDENTIAL_CODING_AGENT_API_KEY_FILE" in variables


@pytest.mark.parametrize(
    ("sets", "message"),
    [
        (("execution.workers[0].name=Coding",), "is not a worker name"),
        (
            (
                "execution.workers[0].name=a",
                "execution.workers[0].endpoint=http://a:9000",
                "execution.workers[1].name=a",
            ),
            "is named twice",
        ),
        (
            ("execution.kind=endpoint", "execution.workers[0].name=a"),
            "endpoint is required",
        ),
    ],
)
def test_a_worker_the_instance_could_not_read_is_refused(
    sets: tuple[str, ...], message: str
) -> None:
    assert message in render_fails(*sets)


def test_the_repository_connector_is_reached_by_the_roles_alone_and_acts_as_the_app(
    rendered: list[dict[str, Any]],
) -> None:
    """Issue #66: the repository channel's connector is deployed with the instance, from the
    control plane's image, as Taktus's own app (ADR-0033); the roles name it as `channel.repo`
    and as the findings connector; it is reached from the roles alone and mounts no token."""
    [connector] = [
        d
        for d in of_kind(rendered, "Deployment")
        if d["metadata"]["labels"]["app.kubernetes.io/component"] == "connector-repository"
    ]
    spec = connector["spec"]["template"]["spec"]
    assert spec["automountServiceAccountToken"] is False
    [container] = spec["containers"]
    roles = [
        d
        for d in of_kind(rendered, "Deployment")
        if d["metadata"]["labels"]["app.kubernetes.io/component"] == "control-plane"
    ]
    assert {container["image"]} == {
        d["spec"]["template"]["spec"]["containers"][0]["image"] for d in roles
    }
    assert container["command"][:3] == ["python", "-m", "taktus.adapters.driven.connectors.github"]
    variables = {v["name"]: v["value"] for v in container["env"]}
    assert set(variables) == {
        "TAKTUS_REPOSITORY_APP_ID",
        "TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE",
        "TAKTUS_CREDENTIAL_REPOSITORY_WEBHOOK_SECRET_FILE",
    }
    [config] = of_kind(rendered, "ConfigMap")
    url = "http://taktus-connector-repository:9100/mcp"
    chat = "http://taktus-connector-chat:9101/mcp"
    assert config["data"]["TAKTUS_CONNECTORS"] == f"channel.repo={url},channel.chat={chat}"
    assert config["data"]["TAKTUS_FINDINGS_CONNECTOR"] == url
    [policy] = [
        d
        for d in of_kind(rendered, "NetworkPolicy")
        if d["metadata"]["name"] == "taktus-connector-repository"
    ]
    [allowed] = policy["spec"]["ingress"]
    [peer] = allowed["from"]
    assert peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"] == "control-plane"
    assert "namespaceSelector" not in peer
    off = render("connectors.repository.enabled=false", "connectors.chat.enabled=false")
    assert not [d for d in off if "connector" in d["metadata"]["name"]]
    assert "TAKTUS_CONNECTORS" not in of_kind(off, "ConfigMap")[0]["data"]


def test_the_platform_and_each_credentials_declaration_are_configuration() -> None:
    """ADR-0052: the platform and the declarations reach the roles as plain settings."""
    documents = render(
        "administration.platform=integration",
        "administration.administers.REPOSITORY_TOKEN=none",
        "administration.administers.DEPLOY_KUBECONFIG=integration",
    )
    [config] = of_kind(documents, "ConfigMap")
    assert config["data"]["TAKTUS_PLATFORM"] == "integration"
    assert config["data"]["TAKTUS_ADMINISTERS"] == (
        "DEPLOY_KUBECONFIG=integration,REPOSITORY_TOKEN=none"
    )
    [plain] = of_kind(render(), "ConfigMap")
    assert "TAKTUS_PLATFORM" not in plain["data"] and "TAKTUS_ADMINISTERS" not in plain["data"]


def test_a_file_of_configuration_is_mounted_into_every_role_and_none_by_default() -> None:
    """ADR-0092: what one tenant measured or shaped — a seed, a finding's form — reaches an
    instance as a file its operator gives, never as a default of the chart."""
    plain = render()
    assert [c["metadata"]["name"] for c in of_kind(plain, "ConfigMap")] == ["taktus-config"]
    documents = render(
        "configFiles.seeds\\.yaml=the-seeds",
        "env.TAKTUS_BUDGET_SEEDS=/etc/taktus/files/seeds.yaml",
    )
    config, files = sorted(of_kind(documents, "ConfigMap"), key=lambda c: c["metadata"]["name"])
    assert files["data"] == {"seeds.yaml": "the-seeds"}
    assert config["data"]["TAKTUS_BUDGET_SEEDS"] == "/etc/taktus/files/seeds.yaml"
    roles = [
        d for d in of_kind(documents, "Deployment") if "taktus-role" in d["metadata"]["labels"]
    ]
    assert len(roles) == 4
    for role in roles:
        spec = role["spec"]["template"]["spec"]
        assert {"name": "config-files", "configMap": {"name": files["metadata"]["name"]}} in spec[
            "volumes"
        ]
        (container,) = spec["containers"]
        assert {
            "name": "config-files",
            "mountPath": "/etc/taktus/files",
            "readOnly": True,
        } in container["volumeMounts"]
    assert "is not a file name" in render_fails("configFiles._a=x")


def test_the_model_output_cap_is_soft_unless_the_operator_sets_it() -> None:
    """ADR-0092 §2: a limit measured on one endpoint is that operator's value, not the chart's."""
    [config] = of_kind(
        render("model.endpoint=https://models.example.net/v1", "model.name=m"), "ConfigMap"
    )
    assert config["data"]["TAKTUS_MODEL_OUTPUT_CAP"] == "soft"


def test_the_ingress_is_off_unless_a_host_is_given(rendered: list[dict[str, Any]]) -> None:
    assert of_kind(rendered, "Ingress") == []


def test_a_named_certificate_secret_is_used_and_none_is_requested() -> None:
    [ingress] = of_kind(
        render("ingress.host=example", "ingress.tls.secretName=existing", "ingress.tls.issuer=x"),
        "Ingress",
    )
    assert ingress["spec"]["tls"] == [{"hosts": ["example"], "secretName": "existing"}]
    annotations = ingress["metadata"].get("annotations") or {}
    assert not [key for key in annotations if key.startswith("cert-manager.io/")]
    [requested] = of_kind(render("ingress.host=example", "ingress.tls.issuer=x"), "Ingress")
    assert requested["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "x"


# --- the values files, without helm ----------------------------------------------------------

HOSTNAME = re.compile(r"(?i)\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b")
ADDRESS = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b|\b[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,}(?:/\d{1,3})?"
)
SECRET_KEY = re.compile(r"(?i)(password|passphrase|token|apikey|api_key|private)$")


def values_files() -> list[Path]:
    files = [CHART / "values.yaml", *sorted((ROOT / "deploy" / "k8s").glob("*.yaml"))]
    assert EXAMPLE in files
    return files


def scalars(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from scalars(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from scalars(value, f"{path}[{index}]")
    else:
        yield path, node


def a_range_not_an_address(text: str) -> bool:
    """A reserved range written as a network — a private, link-local or shared block — names no
    machine. Anything else that parses as an address does."""
    try:
        network = ipaddress.ip_network(text, strict=True)
    except ValueError:
        return False
    if network.prefixlen == 0 or str(network) == "100.64.0.0/10":
        return True
    return network.prefixlen <= 16 and (network.is_private or network.is_link_local)


@pytest.mark.parametrize("path", values_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_values_file_carries_a_value_a_hostname_or_an_address(path: Path) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for where, value in scalars(document):
        if not isinstance(value, str):
            continue
        assert "://" not in value, f"{path.name} {where}: a URL"
        assert not HOSTNAME.search(value), f"{path.name} {where}: a hostname"
        for match in ADDRESS.findall(value):
            assert a_range_not_an_address(match), f"{path.name} {where}: an address"
        if SECRET_KEY.search(where.rsplit(".", 1)[-1]):
            assert value == "", f"{path.name} {where}: a secret's value; name its Secret instead"


# --- the database's backup (ADR-0087, #67) -----------------------------------------------------


def test_the_backup_is_a_daily_cronjob_that_never_overlaps_and_reads_its_secrets_as_files(
    rendered: list[dict[str, Any]],
) -> None:
    [cron] = of_kind(rendered, "CronJob")
    assert cron["metadata"]["namespace"] == RELEASE_NAMESPACE
    assert cron["spec"]["concurrencyPolicy"] == "Forbid"
    assert cron["spec"]["timeZone"] == "Etc/UTC"
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsUser"] == 70
    [container] = pod["containers"]
    assert container["image"] == "taktus-backup:0.1.0"
    env = {v["name"]: v["value"] for v in container["env"]}
    assert env["TAKTUS_BACKUP_RETENTION_DAYS"] == "30"
    assert env["TAKTUS_BACKUP_RECIPIENT"] == ""
    assert env["TAKTUS_DATABASE_URL_FILE"] == "/run/secrets/taktus/database-url/url"
    assert (
        env["TAKTUS_CREDENTIAL_BACKUP_STORE_FILE"] == "/run/secrets/taktus/backup-store/secret_key"
    )
    assert env["TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE"] == (
        "/run/secrets/taktus/backup-store/access_key"
    )


def test_the_backup_archives_the_object_store_from_the_state_volume_read_only(
    rendered: list[dict[str, Any]],
) -> None:
    """The database alone restores an instance whose runs refer to nothing readable (#322)."""
    [cron] = of_kind(rendered, "CronJob")
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    [container] = pod["containers"]
    env = {v["name"]: v["value"] for v in container["env"]}
    assert env["TAKTUS_BACKUP_OBJECTS_DIRECTORY"] == "/var/lib/taktus/objects"
    mounts = {m["name"]: m for m in container["volumeMounts"]}
    assert mounts["state"]["mountPath"] == "/var/lib/taktus" and mounts["state"]["readOnly"]
    volumes = {v["name"]: v for v in pod["volumes"]}
    claim = volumes["state"]["persistentVolumeClaim"]
    assert claim == {"claimName": "taktus-state", "readOnly": True}
    [term] = pod["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    assert term["topologyKey"] == "kubernetes.io/hostname", "the volume is ReadWriteOnce"
    assert term["labelSelector"]["matchLabels"]["app.kubernetes.io/component"] == "control-plane"


def test_without_the_object_store_the_backup_mounts_no_state() -> None:
    [cron] = of_kind(render("backup.objects=false"), "CronJob")
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    [container] = pod["containers"]
    assert "TAKTUS_BACKUP_OBJECTS_DIRECTORY" not in {v["name"] for v in container["env"]}
    assert "state" not in {v["name"] for v in pod["volumes"]} and "affinity" not in pod


def test_the_retention_and_the_recipient_are_configuration() -> None:
    documents = render("backup.retentionDays=7", "backup.recipient=age1example")
    [cron] = of_kind(documents, "CronJob")
    [container] = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    env = {v["name"]: v["value"] for v in container["env"]}
    assert (env["TAKTUS_BACKUP_RETENTION_DAYS"], env["TAKTUS_BACKUP_RECIPIENT"]) == (
        "7",
        "age1example",
    )


def test_the_backup_reaches_the_database_and_the_store_and_nothing_else(
    rendered: list[dict[str, Any]],
) -> None:
    policies = {p["metadata"]["name"]: p["spec"] for p in of_kind(rendered, "NetworkPolicy")}
    backup = policies["taktus-backup"]
    assert backup["policyTypes"] == ["Ingress", "Egress"]
    assert "ingress" not in backup, "nothing reaches the backup"
    dns, database, outside = backup["egress"]
    assert {p["port"] for p in dns["ports"]} == {53}
    assert database["to"][0]["podSelector"]["matchLabels"]["app.kubernetes.io/component"] == (
        "database"
    )
    assert [p["port"] for p in outside["ports"]] == [443]
    assert "10.0.0.0/8" in outside["to"][0]["ipBlock"]["except"]
    admitted = [
        peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
        for peer in policies["taktus-database"]["ingress"][0]["from"]
    ]
    assert admitted == ["control-plane", "migrate", "backup"]


def test_without_the_backup_nothing_of_it_is_rendered() -> None:
    documents = render("backup.enabled=false")
    assert of_kind(documents, "CronJob") == []
    policies = {p["metadata"]["name"]: p["spec"] for p in of_kind(documents, "NetworkPolicy")}
    assert "taktus-backup" not in policies
    assert len(policies["taktus-database"]["ingress"][0]["from"]) == 2


@pytest.mark.parametrize(
    "setting",
    ["backup.store.secret=", "backup.store.endpoint=", "backup.store.bucket=", "backup.image.tag="],
)
def test_a_backup_without_its_store_or_its_version_is_refused(setting: str) -> None:
    assert "backup." in render_fails(setting)
