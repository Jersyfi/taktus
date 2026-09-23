#!/bin/sh
# The first end-to-end, in one command: an issue of this repository becomes a pull request.
#
#     tools/first_run.sh <issue number>
#
# Runs P-02 Refinement and then P-03 Implementation of the dev-orchestration blueprint against
# the repository this checkout was cloned from, with the reference connector, the coding worker
# and a configured model — everything real. It starts the connector and the worker as
# processes, runs each bundle with `taktusctl run`, and stops them. Every run, its ledger and
# its provenance are printed; the log of each process is under $TAKTUS_STATE_DIR/first-run/.
#
# What it needs, as parameters (CREDENTIALS.md); no value is ever an argument or a line here.
# Every credential is named the one way the repository names credentials, `credential.<name>`
# through TAKTUS_CREDENTIAL_<NAME>_FILE (DEC-0018):
#
#   TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE
#       the file that holds the requesting identity's repository token: contents and pull
#       requests write, issues read
#   TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE  or  TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE
#       the file that holds the coding agent's key, or its subscription token
#       (workers/claudecode/README.md); the one that is set decides --auth
#   TAKTUS_MODEL_ENDPOINT, TAKTUS_MODEL_NAME
#       the chat-completions endpoint the model adapter asks and the model it asks for;
#       TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE when the endpoint needs a key
#   TAKTUS_PROVISIONAL_IDENTITY
#       default `default=idn_owner` (DEC-0013)
#
# Optional: TAKTUS_FIRST_RUN_REPOSITORY (owner/name; default: from `git remote get-url origin`),
# TAKTUS_STATE_DIR (default ~/.cache/taktus/taktusctl), TAKTUS_DATABASE_URL to keep the state
# in PostgreSQL. P-03 branches from `main`, as its bundle says.
#
# `.env` in the checkout is read first, if present, so that the variables can live there
# (ignored by git; names in .env.example).
#
# Nothing here writes to the base branch: P-03 opens a pull request, CI decides, a person merges.

set -eu

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

issue="${1:-}"
if [ -z "$issue" ]; then
    echo "usage: tools/first_run.sh <issue number>" >&2
    exit 2
fi

fail() {
    echo "first_run: $1" >&2
    exit 2
}

[ -n "${TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE:-}" ] || fail "TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE is not set: the file that holds the repository token"
[ -r "$TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE" ] || fail "TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE=$TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE cannot be read"
if [ -n "${TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE:-}" ]; then
    auth=api-key
    coding_credential=CODING_AGENT_API_KEY
    coding_file="$TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE"
elif [ -n "${TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE:-}" ]; then
    auth=session
    coding_credential=CODING_AGENT_SESSION
    coding_file="$TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE"
else
    fail "neither TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE nor TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE is set: the coding worker needs one (workers/claudecode/README.md)"
fi
[ -r "$coding_file" ] || fail "$coding_file cannot be read"
[ -n "${TAKTUS_MODEL_ENDPOINT:-}" ] || fail "TAKTUS_MODEL_ENDPOINT is not set: the model P-02 asks for the acceptance criteria"
[ -n "${TAKTUS_MODEL_NAME:-}" ] || fail "TAKTUS_MODEL_NAME is not set"
command -v git >/dev/null 2>&1 || fail "git is not on the path; the coding worker needs it"

origin="$(git remote get-url origin 2>/dev/null || true)"
repository="${TAKTUS_FIRST_RUN_REPOSITORY:-$(printf '%s' "$origin" | sed -E 's#^(https://[^/]+/|git@[^:]+:)##; s#\.git$##')}"
host="$(printf '%s' "$origin" | sed -E 's#^https://([^/]+)/.*#\1#; s#^git@([^:]+):.*#\1#')"
[ -n "$repository" ] && [ -n "$host" ] || fail "the repository cannot be derived from the origin remote; set TAKTUS_FIRST_RUN_REPOSITORY"
clone_url="https://$host/$repository.git"

state="${TAKTUS_STATE_DIR:-$HOME/.cache/taktus/taktusctl}"
logs="$state/first-run"
mkdir -p "$logs"
export TAKTUS_STATE_DIR="$state"
export TAKTUS_PROVISIONAL_IDENTITY="${TAKTUS_PROVISIONAL_IDENTITY:-default=idn_owner}"
export TAKTUS_EXECUTION="${TAKTUS_EXECUTION:-endpoint}"

connector_port="${TAKTUS_FIRST_RUN_CONNECTOR_PORT:-9100}"
worker_port="${TAKTUS_FIRST_RUN_WORKER_PORT:-9010}"
export TAKTUS_CONNECTORS="channel.repo=http://127.0.0.1:$connector_port/mcp"
export TAKTUS_WORKER="http://127.0.0.1:$worker_port"

pids=""
stop() {
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
}
trap stop EXIT INT TERM

echo "first_run: repository $repository, issue #$issue"
echo "first_run: state under $state, logs under $logs"

# The connector, with the requesting identity's token in its environment and nowhere else.
REPOSITORY_TOKEN="$(cat "$TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE")" \
    uv run python -m taktus.adapters.driven.connectors.github \
        --port "$connector_port" --repository "$repository" >"$logs/connector.log" 2>&1 &
pids="$pids $!"

# The coding worker by endpoint, with its credential in its environment (its README) — set
# in a subshell, never on a command line a process listing would show.
(
    export "$coding_credential=$(cat "$coding_file")"
    exec python3 workers/claudecode/worker.py --port "$worker_port" --auth "$auth" \
        --state-dir "$state/coding-worker"
) >"$logs/worker.log" 2>&1 &
pids="$pids $!"

ready() {
    url="$1"; what="$2"; n=0
    until curl -fsS "$url" >/dev/null 2>&1; do
        n=$((n + 1))
        [ "$n" -lt 100 ] || fail "the $what did not become ready; see $logs"
        sleep 0.2
    done
}
ready "http://127.0.0.1:$connector_port/health" connector
ready "http://127.0.0.1:$worker_port/v1/health" "coding worker"

run_bundle() {
    name="$1"; shift
    echo
    echo "first_run: $name"
    status=0
    uv run taktusctl run "$@" >"$logs/$name.txt" 2>&1 || status=$?
    cat "$logs/$name.txt"
    if [ "$status" -ne 0 ]; then
        echo "first_run: $name did not finish (exit $status); the last line above says how to resume" >&2
        exit "$status"
    fi
}

run_bundle P-02 --process blueprints/dev-orchestration/processes/P-02-refinement.yaml \
    --input "issue=$issue"

run_bundle P-03 --process blueprints/dev-orchestration/processes/P-03-implementation.yaml \
    --input "issue=$issue" --input "repository_url=$clone_url" --input "repository_host=$host" \
    --input "coding_credential=$coding_credential"

echo
echo "first_run: done — P-03 opened the pull request; CI decides, a person merges"
