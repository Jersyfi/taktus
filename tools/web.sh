#!/bin/sh
# `make gate-web`: the web app under web/ — its packages from the lock file, its types, its
# tests and its build (ADR-0063).
#
# Without Node on the path the gate skips and says so, as the database tests do without Docker:
# `make gates` needs no Node. CI sets TAKTUS_REQUIRE_NODE, which turns the skip into a failure,
# so that the gate cannot go green by not looking. Prints its duration last (CLAUDE.md §11).
#
# POSIX sh.

set -eu

started=$(date +%s)
if ! command -v npm >/dev/null 2>&1; then
    if [ -n "${TAKTUS_REQUIRE_NODE:-}" ]; then
        tools/preflight.sh node
        exit 1
    fi
    echo "gate-web: skipped — Node is not on the path (make doctor says how to install it)"
    exit 0
fi
cd web
npm ci --no-audit --no-fund
npm run check
npm test
npm run build
echo "gate-web: $(($(date +%s) - started))s"
