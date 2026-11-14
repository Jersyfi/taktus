"""The deployment identity's manifest (deploy/k8s/deployment-identity.yaml, README §1): namespaced
objects only, rights in the two namespaces for every kind the chart renders there and nothing
else, and enough to grant Taktus's own Role, which the cluster refuses to anyone who does not
hold its rights (Kubernetes' prevention of privilege escalation)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from taktus.adapters.driven.execution.kubernetes.api import PERMITTED

from .test_chart import EXECUTION_NAMESPACE, HA, RELEASE_NAMESPACE, render

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "deploy" / "k8s" / "deployment-identity.yaml"
WRITE = {"get", "list", "watch", "create", "update", "patch", "delete"}
RESOURCES = {
    "Secret": ("", "secrets"),
    "ConfigMap": ("", "configmaps"),
    "Service": ("", "services"),
    "ServiceAccount": ("", "serviceaccounts"),
    "PersistentVolumeClaim": ("", "persistentvolumeclaims"),
    "Deployment": ("apps", "deployments"),
    "StatefulSet": ("apps", "statefulsets"),
    "Job": ("batch", "jobs"),
    "CronJob": ("batch", "cronjobs"),
    "Role": ("rbac.authorization.k8s.io", "roles"),
    "RoleBinding": ("rbac.authorization.k8s.io", "rolebindings"),
    "NetworkPolicy": ("networking.k8s.io", "networkpolicies"),
    "Ingress": ("networking.k8s.io", "ingresses"),
    "PodDisruptionBudget": ("policy", "poddisruptionbudgets"),
}


def documents() -> list[dict[str, Any]]:
    text = MANIFEST.read_text(encoding="utf-8")
    text = text.replace("${CONTROL_NAMESPACE}", RELEASE_NAMESPACE)
    text = text.replace("${EXECUTION_NAMESPACE}", EXECUTION_NAMESPACE)
    return [d for d in yaml.safe_load_all(text) if d]


def granted(namespace: str) -> dict[tuple[str, str], set[str]]:
    """(api group, resource) → verbs the deployer's Role grants in the namespace."""
    (role,) = [
        d for d in documents() if d["kind"] == "Role" and d["metadata"]["namespace"] == namespace
    ]
    rights: dict[tuple[str, str], set[str]] = {}
    for rule in role["rules"]:
        for group in rule["apiGroups"]:
            for resource in rule["resources"]:
                rights.setdefault((group, resource), set()).update(rule["verbs"])
    return rights


def test_the_manifest_holds_namespaced_objects_only_and_binds_its_own_account() -> None:
    found = documents()
    assert {d["kind"] for d in found} == {"ServiceAccount", "Secret", "Role", "RoleBinding"}
    assert {d["metadata"]["namespace"] for d in found} == {RELEASE_NAMESPACE, EXECUTION_NAMESPACE}
    for binding in [d for d in found if d["kind"] == "RoleBinding"]:
        assert binding["roleRef"]["kind"] == "Role"
        (subject,) = binding["subjects"]
        assert (subject["name"], subject["namespace"]) == ("taktus-deployer", RELEASE_NAMESPACE)


@pytest.mark.parametrize("namespace", [RELEASE_NAMESPACE, EXECUTION_NAMESPACE])
def test_the_deployer_may_write_every_kind_the_chart_renders_in_each_namespace(
    namespace: str,
) -> None:
    rights = granted(namespace)
    rendered = render(*HA) + render()
    kinds = {d["kind"] for d in rendered if d["metadata"].get("namespace") == namespace}
    assert kinds, "the chart renders something in each namespace"
    for kind in kinds:
        assert WRITE <= rights.get(RESOURCES[kind], set()), f"{kind} in {namespace}"
    for read in ("pods", "pods/log", "events"):
        assert rights[("", read)] == {"get", "list", "watch"}


def test_the_deployer_holds_every_right_it_grants_taktus() -> None:
    """The cluster lets an account create a Role only with rights it holds itself."""
    rights = granted(EXECUTION_NAMESPACE)
    for resource, verb in PERMITTED:
        group = "batch" if resource == "jobs" else ""
        assert verb in rights.get((group, resource), set()), f"{verb} {resource}"
