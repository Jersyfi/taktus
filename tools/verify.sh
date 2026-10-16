#!/bin/sh
# Run what CI would select for this change, and stamp the commit it passed on (ADR-0096 §4).
#
# `make verify` runs it. The lanes come from tools/lanes.py, the code CI's `select` job runs,
# measured against BASE (default origin/main); each lane's make targets run in turn and the
# first failure stops. When all pass on a clean working tree, the commit is written to the
# stamp `.git/taktus-verified`: a session hook refuses `gh pr ready` unless the stamp names
# the head that was pushed (.claude/hooks/ready-needs-verify.sh). A tree with changes not
# committed gets no stamp, because the stamp could not say what was checked.
#
# POSIX sh.

set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE=${BASE:-origin/main}
cd "$ROOT"

lanes=$(python3 tools/lanes.py --base "$BASE")
echo "verify: lanes $lanes (against $BASE)"
for target in $(python3 tools/lanes.py --base "$BASE" --commands); do
    echo "verify: make $target"
    make "$target" BASE="$BASE"
done

stamp="$(git rev-parse --git-dir)/taktus-verified"
if [ -n "$(git status --porcelain)" ]; then
    rm -f "$stamp"
    echo "verify: passed, but the working tree has changes not committed; no stamp written"
    exit 0
fi
git rev-parse HEAD > "$stamp"
echo "verify: passed; $(cat "$stamp") stamped"
