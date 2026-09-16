#!/bin/sh
# Tooling preflight: a gate that fails because a tool is missing says so.
#
# `tools/preflight.sh uv gitleaks` checks that every named tool is on the path. On a miss it
# prints the tool, what it is for, and the one command that installs it, and exits 1 — instead
# of `make: uv: No such file or directory`. `tools/preflight.sh --doctor` reports every tool the
# repository knows and exits 1 if a required one is missing. Every make target depends on the
# tools it needs through `need-<tool>` (Makefile).
#
# POSIX sh, so that it runs before any of the tools it checks for.

set -eu

purpose() {
    case "$1" in
        uv) echo "runs every Python gate: the environment, tests, lint, types, the tools" ;;
        gitleaks) echo "scans the repository for secret values (make gate-secrets)" ;;
        node) echo "JavaScript runtime for the web app under web/; no gate needs it" ;;
        *) echo "unknown tool" ;;
    esac
}

required() {
    case "$1" in
        uv | gitleaks) echo "required" ;;
        node) echo "optional" ;;
        *) echo "unknown" ;;
    esac
}

install_command() {
    case "$1" in
        uv) echo "curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        gitleaks)
            if [ "$(uname -s)" = "Darwin" ]; then
                echo "brew install gitleaks"
            else
                echo "see https://github.com/gitleaks/gitleaks#installing (a single binary per release)"
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
        gitleaks) gitleaks version 2>/dev/null | head -n 1 ;;
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

doctor() {
    status=0
    echo "tooling"
    for tool in uv gitleaks node; do
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
        echo "a required tool is missing; make gates cannot run"
    else
        echo "every required tool is present"
    fi
    return "$status"
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
