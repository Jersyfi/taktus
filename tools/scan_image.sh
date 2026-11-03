#!/bin/sh
# Scan one published image for known vulnerabilities, once per platform (ADR-0173 §2).
#
#   tools/scan_image.sh <image>@sha256:<digest> [platform,...]
#   tools/scan_image.sh --expect-findings <image> [platform,...]
#
# Fails when a vulnerability of severity `high` or above has a fixed version. A finding without
# a fix is printed and does not fail. The scanner is grype from .tools/bin
# (`make image-tools`), or the one TAKTUS_GRYPE names; its configuration is
# deploy/images/grype.yaml. The image is read from its registry; nothing is pulled into the
# local engine. Platforms default to linux/amd64.
#
# --expect-findings is the proof that the scanner can fail (§4): it succeeds only when the scan
# fails on findings, and fails when the scan passes or stops with an error, such as a database
# that did not load.
#
# Exit: 0 passed (or, with --expect-findings, failed on findings as expected); 1 otherwise.
#
# POSIX sh.

set -eu

SEVERITY="high"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
GRYPE=${TAKTUS_GRYPE:-"$ROOT/.tools/bin/grype"}
CONFIG="$ROOT/deploy/images/grype.yaml"

expect=pass
if [ "${1:-}" = "--expect-findings" ]; then
    expect=findings
    shift
fi
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "usage: scan_image.sh [--expect-findings] <image> [platform,...]" >&2
    exit 1
fi
image=$1
platforms=${2:-linux/amd64}
if [ ! -x "$GRYPE" ]; then
    echo "scan_image: no scanner at $GRYPE; \`make image-tools\` installs the pinned one" >&2
    exit 1
fi

failed=0
old_ifs=$IFS
IFS=,
for platform in $platforms; do
    IFS=$old_ifs
    echo "scan_image: $image ($platform), failing on $SEVERITY and above with a fix"
    set +e
    "$GRYPE" "registry:$image" --platform "$platform" --config "$CONFIG" \
        --only-fixed --fail-on "$SEVERITY" --output table
    status=$?
    set -e
    case "$expect-$status" in
        pass-0) ;;
        pass-2) echo "scan_image: $image ($platform) has a fixed $SEVERITY or critical vulnerability" >&2; failed=1 ;;
        pass-*) echo "scan_image: the scan of $image ($platform) stopped with error $status" >&2; failed=1 ;;
        findings-2) echo "scan_image: $image ($platform) failed on findings, as it must" ;;
        findings-0) echo "scan_image: $image ($platform) passed; a scanner that passes a known-vulnerable image is no gate" >&2; failed=1 ;;
        findings-*) echo "scan_image: the scan of $image ($platform) stopped with error $status, not on findings" >&2; failed=1 ;;
    esac
done
IFS=$old_ifs
exit $failed
