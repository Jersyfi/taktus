#!/bin/sh
# Scan the commits of a range for secret values, after proving the scan finds a planted one.
#
#   tools/scan_secrets.sh <base> <head>
#
# CI passes the range its own event names: a pull request's base and head commit, or a push's
# commit before and after. Both are in the run's clone. The gitleaks action looked the range up
# from the host instead, at run time; when a newer push had landed by then, the range ended in a
# commit the clone did not have, and the scan failed as "partial scan" without a finding (#389).
# A base the clone does not have — a new branch's forty zeros, or a commit a force push
# replaced — scans what the head has beyond `main`.
#
# Before the scan, the same binary scans a throwaway repository holding one planted key and
# must report it: a scan that finds nothing because it read nothing fails here instead.
#
# Exit 0: nothing found. Exit 1: a finding, or the scan could not run. Needs .tools/bin/gitleaks
# (tools/install_gitleaks.sh) or gitleaks on the path.

set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
if [ -x "$ROOT/.tools/bin/gitleaks" ]; then
    GITLEAKS="$ROOT/.tools/bin/gitleaks"
else
    GITLEAKS=$(command -v gitleaks) || { echo "scan_secrets: no gitleaks" >&2; exit 1; }
fi
[ $# -eq 2 ] || { echo "usage: scan_secrets.sh <base> <head>" >&2; exit 1; }
base=$1
head=$2

planted=$(mktemp -d)
trap 'rm -rf "$planted"' EXIT
git -C "$planted" init --quiet
# Assembled at run time, so that no file of this repository carries the key the scan must find.
printf 'aws_access_key_id = %s%s\n' "AKIA" "QYLPMN5HHHFPZAM2" > "$planted/config"
git -C "$planted" add config
git -C "$planted" -c user.name=scan -c user.email=scan@localhost commit --quiet -m planted
status=0
"$GITLEAKS" git --no-banner --redact --log-level=error --exit-code=2 "$planted" >/dev/null || status=$?
if [ "$status" -ne 2 ]; then
    echo "scan_secrets: the planted key was not found (exit $status); the scan proves nothing" >&2
    exit 1
fi
echo "scan_secrets: the planted key was found"

has() { git -C "$ROOT" cat-file -e "$1^{commit}" 2>/dev/null; }
has "$head" || { echo "scan_secrets: $head is not in this clone" >&2; exit 1; }
if has "$base"; then
    range="$base..$head"
elif has origin/main; then
    # A new branch (a base of forty zeros), or a force push that replaced the base: everything
    # the head has that `main` has not.
    range="origin/main..$head"
else
    range="-1 $head"
fi
echo "scan_secrets: scanning $range"
exec "$GITLEAKS" git --no-banner --redact -v --exit-code=1 --log-opts="--no-merges $range" "$ROOT"
