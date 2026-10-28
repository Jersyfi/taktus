#!/usr/bin/env bash
# The upgrade test (ADR-0093, ADR-0124): an instance on the previous release, holding a run in
# every state a run can wait in, is upgraded to this checkout, and every run resumes at its
# boundary.
#
#   deploy/docker/upgrade.sh                     # from the release named below
#   TAKTUS_UPGRADE_FROM=v0.2.0-rc.29 \
#   TAKTUS_UPGRADE_IMAGE=<registry>/taktus:0.2.0-rc.29 \
#   TAKTUS_UPGRADE_WORKER_IMAGE=<registry>/taktus-worker-script:0.2.0-rc.29 \
#       deploy/docker/upgrade.sh
#
# The previous release is its own tag's compose files with its own published images; this
# checkout is built here. What it does, in order:
#
#   1. builds this checkout's images first, so that the upgrade itself is only a restart;
#   2. starts the previous release from nothing, with the reference worker of that release;
#   3. leaves five runs, one in each state: finished, waiting for a person, parked in a long
#      wait, halted at its money limit, escalated after its worker step failed;
#   4. runs this checkout's migrations while the previous release still serves, and — when that
#      release reads the schema's range (#330) — checks that it stays ready; then upgrades:
#      the containers are replaced by this checkout's, which migrate on start;
#   5. checks that every run is where it was, and that its ledger's chain is intact;
#   6. continues each one as its operator would — confirms the waiting step, raises the halted
#      run's limit, resumes the escalated one once its cause is gone, and lets the parked one
#      wake — and checks that each finishes, and that no step that had completed before the
#      upgrade started again.
#
# Needs docker with the compose plugin, git, curl and python3. It runs under its own project
# name, so that an instance of the operator's on this machine is not touched. Its containers and
# volumes stay when it ends; TAKTUS_UPGRADE_CLEAN=1 removes this test's own, and only those.
# Exit code 0 when every run resumed at its boundary.
set -euo pipefail
cd "$(dirname "$0")/../.."

from="${TAKTUS_UPGRADE_FROM:-}"
image="${TAKTUS_UPGRADE_IMAGE:-}"
worker_image="${TAKTUS_UPGRADE_WORKER_IMAGE:-}"
if [ -z "$from" ] || [ -z "$image" ] || [ -z "$worker_image" ]; then
    echo "upgrade: set TAKTUS_UPGRADE_FROM (the previous release's tag), TAKTUS_UPGRADE_IMAGE and" >&2
    echo "TAKTUS_UPGRADE_WORKER_IMAGE (its control plane and reference worker images)" >&2
    exit 2
fi
platform="${TAKTUS_UPGRADE_PLATFORM:-}"
export COMPOSE_PROJECT_NAME="${TAKTUS_UPGRADE_PROJECT:-taktus-upgrade}"
export TAKTUS_HTTP_PORT="${TAKTUS_UPGRADE_PORT:-18080}"
api="http://127.0.0.1:${TAKTUS_HTTP_PORT}"
say() { printf '\nupgrade: %s\n' "$*"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git show "${from}:deploy/docker/compose.yml" > "$work/previous.yml"
git show "${from}:deploy/docker/compose.reference-worker.yml" > "$work/previous-worker.yml"
# Both releases read a price table, so that a step's money estimate exists and a money limit can
# halt a run; and a ceiling, so that a person may raise it (ADR-0005 §4).
{
    echo "services:"
    echo "  taktus:"
    echo "    image: ${image}"
    [ -z "$platform" ] || echo "    platform: ${platform}"
    echo "    environment:"
    echo "      TAKTUS_PRICE_TABLE: /app/contracts/model/v1/examples/price-table/valid/a-model-and-compute.json"
    echo "      TAKTUS_RAISE_CEILING: 5 eur"
    echo "  worker:"
    echo "    image: ${worker_image}"
    [ -z "$platform" ] || echo "    platform: ${platform}"
} > "$work/previous-images.yml"
{
    echo "services:"
    echo "  taktus:"
    echo "    environment:"
    echo "      TAKTUS_PRICE_TABLE: /app/contracts/model/v1/examples/price-table/valid/a-model-and-compute.json"
    echo "      TAKTUS_RAISE_CEILING: 5 eur"
} > "$work/current-settings.yml"

previous() {
    docker compose --project-directory deploy/docker -f "$work/previous.yml" \
        -f "$work/previous-worker.yml" -f "$work/previous-images.yml" "$@"
}
current() {
    docker compose --project-directory deploy/docker -f deploy/docker/compose.yml \
        -f deploy/docker/compose.reference-worker.yml -f "$work/current-settings.yml" "$@"
}

say "1. this checkout's images, built before anything starts"
current build

say "2. the previous release, ${from}, from nothing"
deploy/docker/secrets.sh
previous pull --quiet taktus worker
previous up --no-build --detach --wait
identity=idn_upgrade
key="$(previous exec -T taktus taktusctl identity add "$identity" | sed -n 's/.*hand it to the person: //p')"
[ -n "$key" ] || { echo "no account key was issued"; exit 1; }
reader=(-H "Authorization: Bearer ${key}")

say "3. one run in each state"
python3 - "$work" <<'PY'
import json, sys
from pathlib import Path

def rule(step_id, after=None):
    step = {"id": step_id, "method": "rule", "reason": "a fixed value", "rejected": [],
            "exactness": "exact", "checks": [{"kind": "recomputation"}],
            "work": {"rule": "constant", "value": {"step": step_id}}}
    if after:
        step["depends_on"] = [after]
    return step

def worker(command):
    return {"id": "work", "method": "worker", "reason": "a command needs a worker", "rejected": [],
            "exactness": "tolerant", "fallback": {"when": "the assignment fails", "to": "human"},
            "requires": ["shell.script"], "depends_on": ["first"],
            "work": {"task": {"goal": "run one command", "acceptance": ["it ran"],
                              "inputs": {"commands": [command]}}, "max_steps": 2}}

def bundle(name, level, steps, limits=None):
    return {"id": f"upgrade-{name}", "version": "1", "name": f"upgrade {name}",
            "autonomy": {"level": level, "reason": "the upgrade test", "toward_next": "none"},
            "author": "the upgrade test", "reason": "a run in one state, across an upgrade",
            "limits": limits or {"compute": {"seconds": 60, "resource_class": "cpu.small"}},
            "steps": steps}

pause = {"id": "pause", "method": "wait", "reason": "a long pause", "rejected": [],
         "depends_on": ["first"], "work": {"seconds": 200}}
bundles = {
    "finished": bundle("finished", 3, [rule("first"), rule("second", "first")]),
    "waiting": bundle("waiting", 2, [rule("first"), rule("second", "first")]),
    "parked": bundle("parked", 3, [rule("first"), pause, rule("second", "pause")]),
    # A money limit below what the worker step costs at the price table's compute price.
    "halted": bundle("halted", 2, [rule("first"), worker("echo 42")],
                     {"compute": {"seconds": 60, "resource_class": "cpu.small"},
                      "currency": {"eur": 0.000001}}),
    # Fails until the file exists, which the test creates after the upgrade.
    "escalated": bundle("escalated", 2,
                        [rule("first"), worker("test -e /var/lib/taktus/unit/upgrade-go")]),
}
for name, document in bundles.items():
    Path(sys.argv[1], f"{name}.yaml").write_text(json.dumps(document), encoding="utf-8")
PY
for name in finished waiting parked halted escalated; do
    previous cp "$work/${name}.yaml" "taktus:/tmp/upgrade-${name}.yaml" >/dev/null 2>&1
done

submit() { previous exec -T taktus taktusctl submit --process "/tmp/upgrade-$1.yaml" --identity "$identity" "${@:2}" 2>/dev/null | tail -1; }
run_of() { curl -fsS "${reader[@]}" "${api}/runs/$1"; }
state_of() { run_of "$1" | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"], r.get("cause") or "-")'; }
step_state() { run_of "$1" | python3 -c 'import json,sys; r=json.load(sys.stdin); print(next(s["state"] for s in r["step_runs"] if s["step_id"]==sys.argv[1]))' "$2"; }
wait_for() {  # RUN STATE [CAUSE] — up to 180 s
    for _ in $(seq 1 360); do
        read -r s c <<<"$(state_of "$1")"
        if [ "$s" = "$2" ] && { [ -z "${3:-}" ] || [ "$c" = "$3" ]; }; then return 0; fi
        sleep 0.5
    done
    echo "run $1 is ${s} (${c}), not $2 ${3:-}"; run_of "$1"; return 1
}
wait_step() {  # RUN STEP STATE
    for _ in $(seq 1 360); do
        [ "$(step_state "$1" "$2")" = "$3" ] && return 0
        sleep 0.5
    done
    echo "step $2 of run $1 is $(step_state "$1" "$2"), not $3"; run_of "$1"; return 1
}
approve() { submit "$1" --resume "$2" --approve "$3" >/dev/null; }

finished="$(submit finished --approve-raise)"
waiting="$(submit waiting)"
parked="$(submit parked --approve-raise)"
halted="$(submit halted)"
escalated="$(submit escalated)"
wait_for "$finished" finished
wait_for "$waiting" waiting_human person
wait_for "$parked" halted parked
for run in "$halted" "$escalated"; do
    name="$([ "$run" = "$halted" ] && echo halted || echo escalated)"
    wait_step "$run" first waiting_human
    approve "$name" "$run" first
    wait_step "$run" work waiting_human
    approve "$name" "$run" work
done
wait_for "$halted" halted limit
wait_for "$escalated" escalated
for run in "$finished" "$waiting" "$parked" "$halted" "$escalated"; do
    echo "${run}: $(state_of "$run")"
done

# What each run looked like before the upgrade: its state, and how often each step started.
snapshot() {
    for run in "$finished" "$waiting" "$parked" "$halted" "$escalated"; do
        curl -fsS "${reader[@]}" "${api}/runs/${run}/ledger" | python3 -c '
import json, sys
from collections import Counter
ledger = json.load(sys.stdin)
started = Counter(e["refs"].get("step_id") for e in ledger["entries"] if e["kind"] == "step.started")
done = sorted({e["refs"].get("step_id") for e in ledger["entries"]
               if e["kind"] == "step.finished" and e.get("outcome") == "succeeded"})
print(json.dumps({"run": sys.argv[1], "intact": ledger["chain"]["intact"],
                  "started": started, "succeeded": done}))
' "$run"
    done
}
snapshot > "$work/before.txt"
cat "$work/before.txt"

say "4a. this checkout's migrations, while the previous release still serves (ADR-0093)"
# What the cluster's pre-upgrade hook does: the schema moves first, the old process keeps running.
current run --rm --no-deps -T taktus alembic -c migrations/alembic.ini upgrade head
if git show "${from}:src/taktus/adapters/driven/postgres/migrate.py" | grep -q "OLDEST_CODE"; then
    # The previous release reads the range (#330): it stays ready against the migrated schema.
    curl -fsS "${api}/ready" | grep -q '"status": *"ready"' \
        || { echo "the previous release is not ready against the migrated schema"; exit 1; }
    echo "the previous release is ready against this checkout's schema"
else
    echo "${from} predates the range check (#330): its readiness after the migration is not held"
fi

say "4. the upgrade: the containers replaced by this checkout's, migrating on start"
current up --no-build --detach --wait
curl -fsS "${api}/ready" | grep -q '"status": *"ready"' && echo "ready on this checkout"

say "5. every run where it was, its chain intact"
for run in "$finished" "$waiting" "$halted" "$escalated"; do
    echo "${run}: $(state_of "$run")"
done
[ "$(state_of "$finished")" = "finished -" ]
[ "$(state_of "$waiting")" = "waiting_human person" ]
[ "$(state_of "$halted")" = "halted limit" ]
read -r s _ <<<"$(state_of "$escalated")"; [ "$s" = escalated ]
read -r s c <<<"$(state_of "$parked")"
[ "$s" = halted ] && [ "$c" = parked ] || { echo "the parked run woke before the upgrade ended: ${s} ${c}"; exit 1; }

say "6. each run continued, as its operator would"
for name in finished waiting parked halted escalated; do
    current cp "$work/${name}.yaml" "taktus:/tmp/upgrade-${name}.yaml" >/dev/null 2>&1
done
next() { current exec -T taktus taktusctl submit --process "/tmp/upgrade-$1.yaml" --identity "$identity" "${@:2}" 2>/dev/null | tail -1; }
# Whatever waits for a person is confirmed, as the operator would, until the run finishes.
drive() {  # NAME RUN
    for _ in $(seq 1 720); do
        read -r s _ <<<"$(state_of "$2")"
        [ "$s" = finished ] && return 0
        if [ "$s" = waiting_human ]; then
            for step in $(run_of "$2" | python3 -c 'import json,sys; print(" ".join(s["step_id"] for s in json.load(sys.stdin)["step_runs"] if s["state"]=="waiting_human"))'); do
                next "$1" --resume "$2" --approve "$step" >/dev/null
            done
        fi
        sleep 0.5
    done
    echo "run $2 did not finish after the upgrade"; run_of "$2"; return 1
}
echo "waiting: confirmed on this checkout"
drive waiting "$waiting"
echo "halted: its money limit raised"
current exec -T taktus taktusctl resume --run "$halted" --raise 1 --reason "the upgrade test" --identity "$identity" || true
drive halted "$halted"
echo "escalated: its cause removed, then resumed at its boundary"
current exec -T worker touch /var/lib/taktus/unit/upgrade-go
current exec -T taktus taktusctl run --process /tmp/upgrade-escalated.yaml --resume "$escalated" --identity "$identity" || true
drive escalated "$escalated"
echo "parked: wakes on its own"
drive parked "$parked"

say "7. no step that had succeeded before the upgrade started again; every chain intact"
snapshot > "$work/after.txt"
python3 - "$work/before.txt" "$work/after.txt" <<'PY'
import json, sys
before = {r["run"]: r for r in map(json.loads, open(sys.argv[1]))}
after = {r["run"]: r for r in map(json.loads, open(sys.argv[2]))}
for run, now in after.items():
    assert now["intact"], f"{run}: the chain does not verify after the upgrade"
    was = before[run]
    for step in was["succeeded"]:
        assert now["started"].get(step) == was["started"].get(step), (
            f"{run}: step {step} had succeeded before the upgrade and started again"
        )
    print(f"{run}: chain intact; succeeded before the upgrade and not started again: "
          f"{', '.join(was['succeeded']) or 'none'}")
PY

if [ "${TAKTUS_UPGRADE_CLEAN:-}" = 1 ]; then
    current down --volumes
fi
say "held: every run resumed at its boundary after the upgrade from ${from}"
