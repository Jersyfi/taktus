#!/usr/bin/env bash
# The promise of ADR-0002 and ADR-0013 A, verified rather than asserted: from nothing, two
# containers come up in one command; a process runs end to end against the reference worker;
# the application container is killed mid-run (SIGKILL, no shutdown); it is restarted; the run
# resumes at its last step boundary and finishes with every artifact exactly once. On the way
# it checks that the control plane image carries no worker code (DEC-0011): the reference
# worker runs from its own image, layered in by compose.reference-worker.yml.
#
# Needs docker with the compose plugin and curl. Leaves the containers and volumes as it found
# them running; `make down` stops them. Exit code 0 when every step held.
set -euo pipefail
cd "$(dirname "$0")/../.."
compose() { docker compose -f deploy/docker/compose.yml -f deploy/docker/compose.reference-worker.yml "$@"; }
say() { printf '\nverify: %s\n' "$*"; }
port="${TAKTUS_HTTP_PORT:-8080}"
api="http://127.0.0.1:${port}"

say "1. from nothing: secrets, images, two containers (plus the reference worker in its own image), ready"
deploy/docker/secrets.sh
compose up --build --detach --wait
curl -fsS "${api}/health" >/dev/null && echo "health answers"
curl -fsS "${api}/ready" | tee /dev/stderr | grep -q '"status": *"ready"' && echo "ready answers"

say "1b. the control plane image contains no worker code (DEC-0011)"
docker run --rm --entrypoint sh taktus:local -c '
set -e
test ! -e /app/workers || { echo "found /app/workers in the control plane image"; exit 1; }
found="$(find / -xdev \( -path /proc -o -path /sys \) -prune -o \( -path "*/workers/*" -not -path "*/src/taktus/*" -o -name fake_agent.py \) -print 2>/dev/null || true)"
[ -z "$found" ] || { echo "worker code in the control plane image: $found"; exit 1; }
# Every worker of this repository says so in its first lines; the worker port of the control
# plane (src/taktus/ports/worker.py) does not, and belongs there.
found="$(grep -rl "separate deployable, as every worker is" /app 2>/dev/null || true)"
[ -z "$found" ] || { echo "worker code in the control plane image: $found"; exit 1; }
echo "no worker code in the image"'

say "2. a run is queued from inside the container and executed by the daemon"
bundle=/tmp/verify-bundle.yaml
compose exec -T taktus python3 - <<'PY' > "$bundle"
import yaml
with open("examples/processes/six-times-seven.yaml") as handle:
    document = yaml.safe_load(handle)
document["id"] = "verify-compose"
document["limits"] = {"compute": {"seconds": 120, "resource_class": "cpu.small"}}
document["steps"] = [s for s in document["steps"] if s["id"] != "overreach"]
compute = next(s for s in document["steps"] if s["id"] == "compute")
compute["work"]["max_steps"] = 24
prepare = next(s for s in document["steps"] if s["id"] == "prepare-commands")
prepare["work"]["value"] = {"commands": ["expr 6 '*' 7", *[f"echo {n}" for n in range(2, 25)]]}
print(yaml.safe_dump(document))
PY
compose cp "$bundle" taktus:/tmp/verify-bundle.yaml
run_id="$(compose exec -T taktus taktusctl submit --process /tmp/verify-bundle.yaml 2>/dev/null | tail -1)"
echo "run ${run_id}"

state() { curl -fsS "${api}/runs/${run_id}" | python3 -c 'import json,sys; r=json.load(sys.stdin); c=[s for s in r["step_runs"] if s["step_id"]=="compute"][0]; print(r["state"], c["state"], len(c.get("artifacts",[])))'; }
say "3. waiting until the worker step is inside the run with a boundary persisted"
for _ in $(seq 1 120); do
    read -r run_state step_state artifacts <<<"$(state)"
    if [ "$step_state" = "running" ] && [ "$artifacts" -gt 0 ]; then break; fi
    if [ "$run_state" = "finished" ]; then echo "the run finished before it could be killed; raise the command count"; exit 1; fi
    sleep 0.5
done
echo "run ${run_state}, compute ${step_state}, ${artifacts} artifact(s) so far"

say "4. the application container is killed — SIGKILL, no shutdown"
compose kill -s SIGKILL taktus
sleep 1
compose ps taktus | tail -1

say "5. restarted; the run is recovered at its last boundary and finishes"
compose up --detach --wait taktus
for _ in $(seq 1 240); do
    read -r run_state step_state artifacts <<<"$(state)"
    if [ "$run_state" = "finished" ]; then break; fi
    sleep 0.5
done
echo "run ${run_state}, compute ${step_state}, ${artifacts} artifact(s)"
[ "$run_state" = "finished" ] || { echo "the run did not finish after the restart"; exit 1; }

say "6. every artifact once, the ledger recovered and intact"
curl -fsS "${api}/runs/${run_id}/ledger" | python3 -c '
import json, sys
ledger = json.load(sys.stdin)
kinds = [e["kind"] for e in ledger["entries"]]
assert ledger["chain"]["intact"], "the chain does not verify"
assert "run.recovered" in kinds, kinds
assert kinds[-1] == "run.finished", kinds
started = [e for e in ledger["entries"] if e["kind"] == "step.started" and e["refs"].get("step_id") == "compute"]
assert len(started) == 2, "the interrupted step ran twice: once before the kill, once after"
print("ledger:", len(kinds), "entries, chain intact, run.recovered present, compute started twice")
'
curl -fsS "${api}/runs/${run_id}" | python3 -c '
import json, sys
run = json.load(sys.stdin)
compute = [s for s in run["step_runs"] if s["step_id"] == "compute"][0]
ids = [a["id"] for a in compute["artifacts"]]
assert ids == [f"output-{n}" for n in range(1, 25)], ids
assert all(s["state"] == "succeeded" for s in run["step_runs"])
print("artifacts:", len(ids), "each exactly once; every step succeeded")
'
say "held: two containers suffice, a killed container resumes at its step boundary"
