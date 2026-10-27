#!/usr/bin/env bash
# `make verify-first-process`: the path of UC-10.4 without a person, measured as `make start`
# measures it (ADR-0136 §7). A new instance is installed under a compose project of its own,
# from nothing, by deploy/docker/start.py. This script then does what a person does in the web
# app, through the same HTTP surface: it signs in with the account key the install printed,
# reads the gallery, chooses the first process it offers, and rehearses its proposal. The
# install's own clock records the time. The script fails where the rehearsal did not finish, or
# where the time was more than ten minutes.
#
# The account key never reaches the output: the install's output goes to a file in a directory
# only this user may read, removed at the end. The containers are stopped at the end; their
# volumes stay, as every volume does (CLAUDE.md §9), under the project's name.
#
# TAKTUS_FIRST_NO_CACHE=1 builds the image as on a new machine: the base images pulled and no
# cached layer used. A runner of the nightly ring is a new machine either way.
#
# Needs docker with the compose plugin, curl and python3.
set -euo pipefail
cd "$(dirname "$0")/../.."
project="${TAKTUS_FIRST_PROJECT:-taktus-first-$(date +%Y%m%d%H%M%S)}"
port="${TAKTUS_FIRST_PORT:-18480}"
api="http://127.0.0.1:${port}"
work="$(mktemp -d)"
chmod 700 "$work"
compose() { docker compose -f deploy/docker/compose.yml -p "$project" "$@"; }
finish() {
    compose down >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap finish EXIT
say() { printf '\nfirst-process: %s\n' "$*"; }

say "1. installing from nothing as project ${project} on port ${port}, with the clock running"
fresh=()
[ "${TAKTUS_FIRST_NO_CACHE:-}" = 1 ] && fresh=(--no-cache)
python3 deploy/docker/start.py --project "$project" --port "$port" --name "Verification" \
    --record "$work/record.json" --give-up-after 900 ${fresh[@]+"${fresh[@]}"} >"$work/install.out" 2>&1 &
install=$!

say "2. the account key the install printed"
key=""
for _ in $(seq 1 900); do
    key="$(sed -n 's/.*keep it like a password: //p' "$work/install.out" | head -1)"
    [ -n "$key" ] && break
    kill -0 "$install" 2>/dev/null || { echo "the install ended before it printed a key"; grep -v 'tka_' "$work/install.out" | tail -20; exit 1; }
    sleep 1
done
[ -n "$key" ] || { echo "no account key within 15 minutes"; exit 1; }
echo "a key was printed; it is not shown here"
auth=(-H "Authorization: Bearer ${key}")

say "3. the gallery, and the first process it offers"
read -r blueprint process <<<"$(curl -fsS "${auth[@]}" "${api}/gallery" | python3 -c '
import json, sys
for b in json.load(sys.stdin)["blueprints"]:
    for p in b["processes"]:
        if "refused" not in p:
            print(b["id"], p["id"]); sys.exit(0)
sys.exit("the gallery offers no process")')"
echo "chosen: ${process} from ${blueprint}"

say "4. its proposal, rehearsed"
proposal="$(curl -fsS "${auth[@]}" -H 'Content-Type: application/json' -d '{}' \
    "${api}/gallery/${blueprint}/${process}/proposals" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
curl -fsS "${auth[@]}" -H 'Content-Type: application/json' -d '{}' \
    "${api}/processes/${process}/proposals/${proposal}/rehearse" >/dev/null
echo "proposal ${proposal} rehearsing"

say "5. the time the install's clock recorded"
wait "$install" || true
python3 - "$work/record.json" <<'PY'
import json, sys
record = json.load(open(sys.argv[1], encoding="utf-8"))
shown = ("seconds", "machine", "build_cache", "within_ten_minutes")
print(json.dumps({k: record[k] for k in shown}, indent=2))
finished = record["stages"]["rehearsal_finished_at"]
assert finished, "the rehearsal did not finish"
assert record["within_ten_minutes"], f"{record['seconds']['total']} s: more than ten minutes"
print(f"first-process: a first rehearsed process {record['seconds']['total']} s after the install began")
PY
