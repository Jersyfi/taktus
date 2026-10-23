#!/usr/bin/env bash
# The chart on a real cluster (#395, ADR-0096 §1 ring 4): installed from this checkout into a
# kind cluster, with the database it deploys, migrated, and every role ready.
#
#   deploy/k8s/kind.sh            # needs docker, kind, kubectl and helm on the path
#
# What it does, in order:
#
#   1. builds this checkout's control plane image and loads it into the cluster;
#   2. creates the two namespaces and the database's Secrets, with a password generated here
#      and never printed;
#   3. installs the chart, profile `small`, with a database of 1 Gi; helm returns when the
#      migration, a hook after the install, has completed;
#   4. waits for the control plane's rollout;
#   5. asks the control plane's readiness from inside its pod, and fails unless it answers 200.
#
# The cluster is the one `kubectl` points at; TAKTUS_KIND_CLUSTER names a kind cluster to load
# the image into (default `kind`). Nothing is deleted: the namespaces stay for inspection.
# Exit code 0 when the instance is ready.
set -euo pipefail
cd "$(dirname "$0")/../.."

cluster="${TAKTUS_KIND_CLUSTER:-kind}"
release=taktus
namespace=taktus
execution=taktus-execution
tag="0.0.0-kind"
image="taktus:${tag}"

say() { echo "kind: $*"; }

say "building ${image}"
docker build --quiet -f deploy/docker/Dockerfile -t "${image}" . > /dev/null
kind load docker-image "${image}" --name "${cluster}"

for ns in "${namespace}" "${execution}"; do
    kubectl get namespace "${ns}" > /dev/null 2>&1 || kubectl create namespace "${ns}"
    kubectl label --overwrite namespace "${ns}" pod-security.kubernetes.io/enforce=restricted > /dev/null
done

if ! kubectl -n "${namespace}" get secret taktus-database > /dev/null 2>&1; then
    password="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
    kubectl -n "${namespace}" create secret generic taktus-database \
        --from-literal=password="${password}" \
        --from-literal=url="postgresql://taktus:${password}@taktus-database:5432/taktus" \
        > /dev/null
    unset password
fi

say "installing the chart"
helm upgrade --install "${release}" deploy/k8s/chart --namespace "${namespace}" \
    --set profile=small \
    --set image.repository=taktus --set image.tag="${tag}" --set image.pullPolicy=Never \
    --set execution.namespace="${execution}" \
    --set execution.image="${image}" \
    --set database.passwordSecret=taktus-database --set database.passwordKey=password \
    --set database.urlSecret=taktus-database --set database.urlKey=url \
    --set database.size=1Gi --set state.size=1Gi \
    --timeout 10m

say "waiting for the control plane"
kubectl -n "${namespace}" rollout status deployment --timeout=5m
kubectl -n "${namespace}" get pods
pod="$(kubectl -n "${namespace}" get pods -l app.kubernetes.io/component=control-plane \
    -o jsonpath='{.items[0].metadata.name}')"
code="$(kubectl -n "${namespace}" exec "${pod}" -- python3 -c \
    'import urllib.request as u; print(u.urlopen("http://127.0.0.1:8080/ready").status)')"
if [ "${code}" != "200" ]; then
    say "readiness answered ${code}"
    exit 1
fi
say "ready"
