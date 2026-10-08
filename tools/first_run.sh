#!/bin/sh
# The first end-to-end, in one command: an issue of this repository becomes a pull request.
#
#     tools/first_run.sh <issue number> [--only P-02|P-03 | --from P-02|P-03] [--resume RUN_ID]
#
# Runs P-02 Refinement and then P-03 Implementation of the dev-orchestration blueprint against
# the repository this checkout was cloned from, with the reference connector, the coding worker
# and a configured model — everything real. It starts the connector and the worker as
# processes, runs each bundle with `taktusctl run`, and stops them. Every run, its ledger and
# its provenance are printed; the log of each process is under $TAKTUS_STATE_DIR/first-run/.
#
# Run again, which is the normal case after an attempt found a defect (issue #30):
#
#   --only P-03      runs P-03 alone, with the same processes started the same way;
#                    --only P-02 runs P-02 alone. --from P-03 is the same as --only P-03,
#                    --from P-02 is the default.
#   --resume RUN_ID  continues a halted or escalated run of the bundle --only names, with the
#                    connector and the worker started again; `taktusctl run --resume` alone
#                    would find neither running.
#
# When P-02 stops at its admission because the issue already carries every section of the ready
# standard, or P-02 already wrote them as a comment, that is "already done", not a failure: the
# script says so and goes on to P-03. Any other stop of P-02 ends the script. P-03 admits only
# an issue that meets the ready standard (docs/process/README.md): P-02 writes a comment, and a
# person puts the sections into the issue and adds the label `ready` before P-03 can run.
#
# The branch P-03 creates, taktus/issue-<n>, carries the idempotency key of the run that made
# it. A new run has a new key, so a branch left by an earlier attempt makes the new run end
# `conflict` at create-branch — after it has paid for the coding step. The script looks for
# that branch before it starts anything and stops with the two ways on: resume the run that
# made it, or delete the branch and start again. It never deletes a branch itself.
#
# P-03's pull request description ends with the section this repository generates for every
# description, `## Needed from the owner` (ADR-0028). The script generates it from the register
# of `main` — the base P-03 branches from — with `tools/check_status.py --print`, and hands it
# to the run as the input `closing_section`; the run appends it after the worker's summary, by
# a template. A language model never writes it (issue #34).
#
# What it needs, as parameters (CREDENTIALS.md); no value is ever an argument or a line here.
# Every credential is named the one way the repository names credentials, `credential.<name>`
# through TAKTUS_CREDENTIAL_<NAME>_FILE (DEC-0018):
#
#   TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE
#       the file that holds the requesting identity's repository token: contents and pull
#       requests write, issues write (P-02 comments, P-03 claims an issue with a label)
#   TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE  or  TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE
#       the file that holds the coding agent's key, or its subscription token
#       (workers/claudecode/README.md); the one that is set decides --auth
#   TAKTUS_MODEL_ENDPOINT, TAKTUS_MODEL_NAME
#       the chat-completions endpoint the model adapter asks and the model it asks for;
#       TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE when the endpoint needs a key.
#       TAKTUS_MODEL_OUTPUT_CAP, when not set, is derived: the model contract's check M-03 is run
#       against the endpoint — two calls of a few tokens — and the limit is declared `hard` when
#       the endpoint holds it, `soft` otherwise (contracts/model/v1 §3). Nobody declares it by hand.
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
#
# WHAT THIS DOES NOT ISOLATE (DEC-0022). The worker is started here as a plain process on this
# machine, reached by endpoint, so nothing stands between the coding agent and whatever this
# machine can reach: not the frame's allowed_hosts, not the resource limits. P-03 declares
# autonomy level 4, and the isolation half of that level is the operator's here, not the
# core's — the core cannot check a worker it did not start. This is a development command.
# An operating deployment runs the unit through the `container` or `cluster` execution kind,
# where the frame is enforced.

set -eu

# What `taktusctl run` prints when a run stops for the two reasons this script tells apart from
# any other failure. tests/integration/test_dev_orchestration.py holds both against the real
# output, so that a change of wording there fails a test and not a live run.
#
# P-02 refused the issue because it has nothing to write: an earlier run of P-02 wrote its
# comment (`admit`), or the issue carries every section of the ready standard (`missing`).
P02_ALREADY_REFINED="(admit +rule +exact +failed .*condition 1 does not hold: .*Written by Taktus, process P-02 Refinement'?, which it must not|missing +rule +exact +failed .*carries every section already)"
# P-03 found the branch it would create, carrying another run's key.
P03_LEFTOVER_BRANCH="repository\.branches\.create failed: conflict .*exists and was not created for this step"

usage="usage: tools/first_run.sh <issue number> [--only P-02|P-03 | --from P-02|P-03] [--resume RUN_ID]"

fail() {
    echo "first_run: $1" >&2
    exit 2
}

issue=""
only=""
from=""
resume=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --only | --from | --resume)
            [ "$#" -ge 2 ] || fail "$1 needs a value; $usage"
            case "$1" in
                --only) only="$2" ;;
                --from) from="$2" ;;
                --resume) resume="$2" ;;
            esac
            shift 2
            ;;
        -h | --help)
            echo "$usage"
            exit 0
            ;;
        -*) fail "unknown option $1; $usage" ;;
        *)
            [ -z "$issue" ] || fail "one issue at a time; $usage"
            issue="$1"
            shift
            ;;
    esac
done

case "$issue" in
    '' | *[!0-9]*) fail "$usage" ;;
esac
for bundle in "$only" "$from"; do
    case "$bundle" in
        '' | P-02 | P-03) ;;
        *) fail "there is no bundle $bundle here: P-02 or P-03" ;;
    esac
done
[ -z "$only" ] || [ -z "$from" ] || fail "--only and --from exclude each other"
[ -z "$resume" ] || [ -n "$only" ] || fail "--resume continues one run: name its bundle with --only P-02 or --only P-03"

run_p02=yes
run_p03=yes
[ "$only" != P-03 ] && [ "$from" != P-03 ] || run_p02=no
[ "$only" != P-02 ] || run_p03=no

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

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
if [ "$run_p02" = yes ]; then
    [ -n "${TAKTUS_MODEL_ENDPOINT:-}" ] || fail "TAKTUS_MODEL_ENDPOINT is not set: the model P-02 asks for the missing sections"
    [ -n "${TAKTUS_MODEL_NAME:-}" ] || fail "TAKTUS_MODEL_NAME is not set"
fi
if [ "$run_p02" = yes ] && [ -z "${TAKTUS_MODEL_OUTPUT_CAP:-}" ]; then
    # Whether the endpoint holds the output limit a call sets is a fact about the provider; it is
    # checked, not assumed (M-03). The key reaches the check through a variable of this process only.
    declaration="$(mktemp)"
    printf '%s' '{"contract":"model/v1","input_count":"upper_bound","output_cap":"hard","usage_kinds":["input","output"],"billing":"per_token"}' >"$declaration"
    key=""
    if [ -n "${TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE:-}" ]; then key="$(cat "$TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE")"; fi
    if TAKTUS_FIRST_RUN_MODEL_KEY="$key" uv run taktusctl conformance run --contract model/v1 \
        --endpoint "$TAKTUS_MODEL_ENDPOINT" --model "$TAKTUS_MODEL_NAME" \
        --declaration "$declaration" --credential TAKTUS_FIRST_RUN_MODEL_KEY --timeout 60 >/dev/null 2>&1; then
        export TAKTUS_MODEL_OUTPUT_CAP=hard
        echo "model: the endpoint holds the output limit a call sets (M-03): declared hard" >&2
    else
        export TAKTUS_MODEL_OUTPUT_CAP=soft
        echo "model: the endpoint did not show it holds the output limit (M-03): declared soft" >&2
    fi
    rm -f "$declaration"
    unset key
fi
command -v git >/dev/null 2>&1 || fail "git is not on the path; the coding worker needs it"

origin="$(git remote get-url origin 2>/dev/null || true)"
repository="${TAKTUS_FIRST_RUN_REPOSITORY:-$(printf '%s' "$origin" | sed -E 's#^(https://[^/]+/|git@[^:]+:)##; s#\.git$##')}"
host="$(printf '%s' "$origin" | sed -E 's#^https://([^/]+)/.*#\1#; s#^git@([^:]+):.*#\1#')"
[ -n "$repository" ] && [ -n "$host" ] || fail "the repository cannot be derived from the origin remote; set TAKTUS_FIRST_RUN_REPOSITORY"
clone_url="https://$host/$repository.git"
branch="taktus/issue-$issue"

# The advice for a branch an earlier attempt left, with the run that made it when its head
# commit names one: the key in its trailer is taktus:<run id>:<step id>:<attempt>.
leftover_branch() {
    made_by=""
    if GIT_TERMINAL_PROMPT=0 git fetch --quiet "$clone_url" "refs/heads/$branch" 2>/dev/null; then
        made_by="$(git log -1 --format=%B FETCH_HEAD | sed -n 's/^Taktus-Idempotency-Key: taktus:\([^:]*\):.*/\1/p' | head -n 1)"
    fi
    {
        echo "first_run: the branch $branch exists on $repository, left by an earlier attempt${made_by:+ (run $made_by)}."
        echo "  It carries that run's idempotency key, so a new run of P-03 would end 'conflict' at"
        echo "  create-branch, after paying for the coding step. Two ways on:"
        echo "  - resume the run that made it; its state must be on this machine, under $state:"
        echo "        tools/first_run.sh $issue --only P-03 --resume ${made_by:-<run id>}"
        echo "  - or delete the branch on the repository, and start again:"
        echo "        tools/first_run.sh $issue --only P-03"
        echo "  This script never deletes a branch."
    } >&2
}

# The section every pull request description of this repository ends with, generated from the
# register of main — the base P-03 branches from — rather than from whatever this checkout
# holds. main is fetched first; if that fails, the origin/main last fetched is used, and without
# one this checkout.
closing_section() {
    GIT_TERMINAL_PROMPT=0 git fetch --quiet origin main 2>/dev/null ||
        echo "first_run: could not fetch main; the closing section comes from the last fetched origin/main" >&2
    ref=origin/main
    git rev-parse --verify --quiet "$ref^{commit}" >/dev/null || ref=HEAD
    scratch="$(mktemp -d)"
    git archive "$ref" tools/check_status.py docs/decisions/open | tar -x -C "$scratch"
    block="$(python3 "$scratch/tools/check_status.py" --print)"
    rm -rf "$scratch"
    printf '## Needed from the owner\n\n%s\n' "$block"
}

state="${TAKTUS_STATE_DIR:-$HOME/.cache/taktus/taktusctl}"
logs="$state/first-run"
mkdir -p "$logs"
export TAKTUS_STATE_DIR="$state"
export TAKTUS_PROVISIONAL_IDENTITY="${TAKTUS_PROVISIONAL_IDENTITY:-default=idn_owner}"
export TAKTUS_EXECUTION="${TAKTUS_EXECUTION:-endpoint}"

echo "first_run: repository $repository, issue #$issue"
echo "first_run: state under $state, logs under $logs"

# Before anything starts or costs: a new P-03 run cannot create a branch that already exists.
if [ "$run_p03" = yes ] && [ -z "$resume" ]; then
    if heads="$(GIT_TERMINAL_PROMPT=0 git ls-remote --heads "$clone_url" "refs/heads/$branch" 2>/dev/null)"; then
        if [ -n "$heads" ]; then
            leftover_branch
            exit 2
        fi
    else
        echo "first_run: could not ask $clone_url whether $branch exists; going on" >&2
    fi
fi

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

# One bundle with `taktusctl run`; its output is printed and kept under $logs/<name>.txt. The
# exit status is the command's: 0 finished, 3 halted or escalated, 2 not runnable.
run_bundle() {
    name="$1"; shift
    echo
    echo "first_run: $name"
    code=0
    uv run taktusctl run "$@" >"$logs/$name.txt" 2>&1 || code=$?
    cat "$logs/$name.txt"
    return "$code"
}

# How to continue a run that stopped, with the processes started again by this script.
did_not_finish() {
    name="$1"; code="$2"
    run_id="$(sed -n 's/^run \(run_[A-Za-z0-9_]*\) .*/\1/p' "$logs/$name.txt" | head -n 1)"
    echo "first_run: $name did not finish (exit $code)" >&2
    if [ -n "$run_id" ]; then
        echo "first_run: to continue it once the cause is dealt with: tools/first_run.sh $issue --only $name --resume $run_id" >&2
    fi
    exit "$code"
}

p02_process=blueprints/dev-orchestration/processes/P-02-refinement.yaml
p03_process=blueprints/dev-orchestration/processes/P-03-implementation.yaml

if [ "$run_p02" = yes ]; then
    if [ -n "$resume" ]; then
        set -- --resume "$resume"
    else
        set -- --input "issue=$issue"
    fi
    status=0
    run_bundle P-02 --process "$p02_process" "$@" || status=$?
    if [ "$status" -eq 3 ] && grep -Eq "$P02_ALREADY_REFINED" "$logs/P-02.txt"; then
        echo
        echo "first_run: P-02 stopped at its admission because the issue already carries its sections, or P-02 wrote them before — already done, not failed"
    elif [ "$status" -ne 0 ]; then
        did_not_finish P-02 "$status"
    fi
fi

if [ "$run_p03" = yes ]; then
    if [ -n "$resume" ]; then
        set -- --resume "$resume"
    else
        closing="$(closing_section)"
        set -- --input "issue=$issue" --input "records_path=docs/decisions/open" \
            --input "repository_url=$clone_url" --input "repository_host=$host" \
            --input "coding_credential=$coding_credential" --input "closing_section=$closing"
    fi
    status=0
    run_bundle P-03 --process "$p03_process" "$@" || status=$?
    if [ "$status" -ne 0 ]; then
        if grep -Eq "$P03_LEFTOVER_BRANCH" "$logs/P-03.txt"; then
            leftover_branch
        fi
        did_not_finish P-03 "$status"
    fi
    echo
    echo "first_run: done — P-03 opened the pull request; CI decides, a person merges"
else
    echo
    echo "first_run: done"
fi
