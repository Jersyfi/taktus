#!/bin/sh
# Install the pinned helm into .tools/bin, the same version locally and in CI.
#
# `make helm` runs it. The chart's test (tests/governance/test_chart.py) uses .tools/bin/helm
# before a helm on the path, so that what CI checks is what a checkout checks. The archive is
# taken from the project's release host and refused unless its SHA-256 is the one written here:
# a new version is a change to this file, with the digests the release publishes.
#
# POSIX sh; needs curl, tar and shasum or sha256sum.

set -eu

VERSION="v4.2.4"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ROOT/.tools/bin"

case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) echo "install_helm: no pinned build for $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64 | amd64) arch=amd64 ;;
    arm64 | aarch64) arch=arm64 ;;
    *) echo "install_helm: no pinned build for $(uname -m)" >&2; exit 1 ;;
esac

case "$os-$arch" in
    darwin-arm64) digest=d747eb4e28bd2727173d15b759fa0a17822291ec09db7ced3d55af290a3661a2 ;;
    darwin-amd64) digest=6c163d687ca03c3b5c01928e53bbbcf9518278f47ce7a2f249a5a08e8bdaa2bc ;;
    linux-amd64) digest=c306b46f719b0a4da32d0f78ee21bf90ce8d602f15b22ab753f0674d1670a7f3 ;;
    linux-arm64) digest=564de2191b881e9f71b5606b25345821ea1682f06ab90499d3ab22b530176da1 ;;
esac

if [ -x "$DEST/helm" ] && "$DEST/helm" version --short 2>/dev/null | grep -q "^$VERSION"; then
    echo "helm $VERSION is in .tools/bin"
    exit 0
fi

archive="helm-$VERSION-$os-$arch.tar.gz"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -sSfL -o "$work/$archive" "https://get.helm.sh/$archive"

if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$work/$archive" | cut -d" " -f1)
else
    actual=$(shasum -a 256 "$work/$archive" | cut -d" " -f1)
fi
if [ "$actual" != "$digest" ]; then
    echo "install_helm: $archive has SHA-256 $actual, expected $digest; refused" >&2
    exit 1
fi

tar -xzf "$work/$archive" -C "$work"
mkdir -p "$DEST"
mv "$work/$os-$arch/helm" "$DEST/helm"
chmod 755 "$DEST/helm"
echo "helm $VERSION installed in .tools/bin"
