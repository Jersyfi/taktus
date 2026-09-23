#!/bin/sh
# Tooling preflight: a gate that fails because a tool is missing says so.
#
# `tools/preflight.sh uv gitleaks` checks that every named tool is on the path. On a miss it
# prints the tool, what it is for, and the one command that installs it, and exits 1 — instead
# of `make: uv: No such file or directory`. Every make target depends on the tools it needs
# through `need-<tool>` (Makefile).
#
# `tools/preflight.sh --doctor` reports two levels and says which is incomplete: the system
# tools (uv, git, gitleaks; docker and node are optional), and the project environment — the tools the gates
# actually invoke through `uv run` (ruff, mypy, pytest, lint-imports, taktusctl), which live
# in .venv and not on the path. Exit 1 if either level is incomplete.
#
# POSIX sh, so that it runs before any of the tools it checks for.

set -eu

purpose() {
    case "$1" in
        uv) echo "runs every Python gate: the environment, tests, lint, types, the tools" ;;
        git) echo "used by make gate-docs (checkdocs.py) and the coding worker to inspect the repository" ;;
        gitleaks) echo "scans the repository for secret values (make gate-secrets)" ;;
        docker) echo "runs the development database (make db-up) and the PostgreSQL tests; without it those tests skip" ;;
        node) echo "JavaScript runtime for the web app under web/; no gate needs it" ;;
        *) echo "unknown tool" ;;
    esac
}

required() {
    case "$1" in
        uv | git | gitleaks) echo "required" ;;
        docker | node) echo "optional" ;;
        *) echo "unknown" ;;
    esac
}

install_command() {
    case "$1" in
        uv) echo "curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        git)
            if [ "$(uname -s)" = "Darwin" ]; then
                echo "xcode-select --install (or brew install git)"
            else
                echo "see https://git-scm.com/downloads/linux (your distribution's git package)"
            fi
            ;;
        gitleaks)
            if [ "$(uname -s)" = "Darwin" ]; then
                echo "brew install gitleaks"
            else
                echo "see https://github.com/gitleaks/gitleaks#installing (a single binary per release)"
            fi
            ;;
        docker)
            if [ "$(uname -s)" = "Darwin" ]; then
                echo "brew install --cask docker (or Docker Desktop / OrbStack)"
            else
                echo "see https://docs.docker.com/engine/install/"
            fi
            ;;
        node)
            if [ "$(uname -s)" = "Darwin" ]; then
                echo "brew install node"
            else
                echo "see https://nodejs.org/en/download (or your distribution's package)"
            fi
            ;;
        *) echo "-" ;;
    esac
}

version_of() {
    case "$1" in
        uv) uv --version 2>/dev/null | head -n 1 | cut -d" " -f1-2 ;;
        git) git --version 2>/dev/null | head -n 1 | cut -d" " -f1-3 ;;
        gitleaks) gitleaks version 2>/dev/null | head -n 1 ;;
        docker) docker --version 2>/dev/null | head -n 1 | cut -d" " -f1-3 | tr -d , ;;
        node) node --version 2>/dev/null | head -n 1 ;;
        *) echo "" ;;
    esac
}

present() {
    command -v "$1" >/dev/null 2>&1
}

check() {
    tool="$1"
    if present "$tool"; then
        return 0
    fi
    echo "missing: $tool — $(purpose "$tool")" >&2
    echo "  install: $(install_command "$tool")" >&2
    return 1
}

project_env() {
    echo "${UV_PROJECT_ENVIRONMENT:-.venv}"
}

# The tools the gates run through `uv run`; each must exist in the project environment.
PROJECT_TOOLS="ruff mypy pytest lint-imports taktusctl"

project_purpose() {
    case "$1" in
        ruff) echo "lint and format (make lint)" ;;
        mypy) echo "types (make lint)" ;;
        pytest) echo "every test gate and make test" ;;
        lint-imports) echo "architecture contracts (make gate-arch)" ;;
        taktusctl) echo "the command line; tests/conformance and tests/integration run it" ;;
        *) echo "" ;;
    esac
}

doctor() {
    status=0
    echo "system tools"
    for tool in uv git gitleaks docker node; do
        need="$(required "$tool")"
        if present "$tool"; then
            printf '  %-8s %-9s %-18s %s\n' "ok" "$tool" "$(version_of "$tool")" "$(purpose "$tool")"
        else
            printf '  %-8s %-9s %-18s %s (%s)\n' "missing" "$tool" "-" "$(purpose "$tool")" "$need"
            printf '  %-8s %-9s install: %s\n' "" "" "$(install_command "$tool")"
            if [ "$need" = "required" ]; then
                status=1
            fi
        fi
    done
    if [ "$status" -ne 0 ]; then
        echo "  -> incomplete: a required system tool is missing; make gates cannot run"
    else
        echo "  -> complete"
    fi
    env_status=0
    env_dir="$(project_env)"
    echo "project environment ($env_dir)"
    for tool in $PROJECT_TOOLS; do
        if [ -x "$env_dir/bin/$tool" ]; then
            printf '  %-8s %-13s %s\n' "ok" "$tool" "$(project_purpose "$tool")"
        else
            printf '  %-8s %-13s %s\n' "missing" "$tool" "$(project_purpose "$tool")"
            env_status=1
        fi
    done
    if [ "$env_status" -ne 0 ]; then
        echo "  -> incomplete: run \`make install\` (every gate target does this itself when needed)"
    else
        echo "  -> complete"
    fi
    if [ "$status" -ne 0 ] || [ "$env_status" -ne 0 ]; then
        return 1
    fi
    return 0
}

if [ "$#" -eq 0 ]; then
    echo "usage: tools/preflight.sh <tool>... | --doctor" >&2
    exit 2
fi
if [ "$1" = "--doctor" ]; then
    doctor
    exit $?
fi
failed=0
for tool in "$@"; do
    case "$(required "$tool")" in
        unknown)
            echo "preflight: unknown tool '$tool'; add it to tools/preflight.sh" >&2
            exit 2
            ;;
    esac
    check "$tool" || failed=1
done
exit "$failed"
