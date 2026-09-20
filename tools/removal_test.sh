#!/bin/sh
# The removal test, for every configured integration, in one command.
#
#     tools/removal_test.sh [--with-example]
#
# Runs S-01 Removal test of the self-operation blueprint once per integration this instance is
# configured with (blueprints/self-operation/processes/S-01-removal-test.yaml): each run
# withholds one integration, exercises the registered processes that use it, restores it and
# records the verdict — broke, changed, exception — in the ledger as `removal.tested` and in
# the adapter's maturity. The scheduler will start these runs weekly from the bundle's trigger
# once it acts on triggers (0.2.0); until then this script is what the weekly job calls
# (.github/workflows/removal-test.yml), and what a person runs by hand.
#
# What it needs: the same configuration the instance runs with (TAKTUS_WORKER or
# TAKTUS_EXECUTION, TAKTUS_CONNECTORS, TAKTUS_MODEL_*, TAKTUS_DATABASE_URL to keep the state in
# PostgreSQL; .env is read first if present) and TAKTUS_PROVISIONAL_IDENTITY (default
# `default=idn_owner`, DEC-0013). The integrations to exercise are read from the instance
# through the loopback connector, never listed here.
#
# `--with-example` registers examples/processes/six-times-seven.yaml first, so that an
# installation with no process of its own still has one to exercise — that is what the weekly
# job does against the reference worker. `--worker-port N` (default 9000) is where
# `--with-example` starts the reference worker when TAKTUS_WORKER is not set.
#
# Exit code: 0 when every run finished, whatever the verdicts — a verdict is a result, not a
# failure; 3 when a run halted or escalated, and the output says how to resume it.

set -eu

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

with_example=0
worker_port=9000
while [ $# -gt 0 ]; do
    case "$1" in
        --with-example) with_example=1 ;;
        --worker-port) shift; worker_port="$1" ;;
        *) echo "usage: tools/removal_test.sh [--with-example] [--worker-port N]" >&2; exit 2 ;;
    esac
    shift
done

fail() {
    echo "removal_test: $1" >&2
    exit 2
}

state="${TAKTUS_STATE_DIR:-$HOME/.cache/taktus/taktusctl}"
logs="$state/removal-test"
mkdir -p "$logs"
export TAKTUS_STATE_DIR="$state"
export TAKTUS_PROVISIONAL_IDENTITY="${TAKTUS_PROVISIONAL_IDENTITY:-default=idn_owner}"
export TAKTUS_EXECUTION="${TAKTUS_EXECUTION:-endpoint}"

pids=""
stop() {
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
}
trap stop EXIT INT TERM

bundle=blueprints/self-operation/processes/S-01-removal-test.yaml
example=examples/processes/six-times-seven.yaml

if [ "$with_example" -eq 1 ]; then
    if [ -z "${TAKTUS_WORKER:-}" ] && [ "$TAKTUS_EXECUTION" = endpoint ]; then
        python3 workers/script/worker.py --port "$worker_port" >"$logs/worker.log" 2>&1 &
        pids="$pids $!"
        export TAKTUS_WORKER="http://127.0.0.1:$worker_port"
        n=0
        until curl -fsS "$TAKTUS_WORKER/v1/health" >/dev/null 2>&1; do
            n=$((n + 1))
            [ "$n" -lt 100 ] || fail "the reference worker did not become ready; see $logs/worker.log"
            sleep 0.2
        done
    fi
    # Registering is running: the bundle is stored when the run is created, and one step is
    # enough. The run is left halted; the removal test rehearses the version, not this run.
    uv run taktusctl run --process "$example" --stop-after 1 >"$logs/register-example.txt" 2>&1 || true
fi

echo "removal_test: state under $state, logs under $logs"

# The integrations are read from the instance, not listed here: one run of S-01 per entry the
# loopback connector's `orchestrator.integrations.list` answers. Until a command lists them,
# the known identifiers of this version are asked in turn, and one that is not configured is
# skipped when its first step says so.
status=0
for integration in worker.endpoint worker.process worker.container model.endpoint persistence.database \
        $(printf '%s' "${TAKTUS_CONNECTORS:-}" | tr ',' '\n' | sed -E 's/=.*//; s/^[[:space:]]*//; /^$/d; s/^/connector./'); do
    echo
    echo "removal_test: $integration"
    out="$logs/$integration.txt"
    if uv run taktusctl run --process "$bundle" --input "integration=$integration" >"$out" 2>&1; then
        cat "$out"
    else
        code=$?
        if grep -q "not_found" "$out"; then
            echo "removal_test: $integration is not configured in this instance; skipped"
        else
            cat "$out"
            echo "removal_test: $integration did not finish (exit $code); the last line above says how to resume" >&2
            status=3
        fi
    fi
done
exit "$status"
