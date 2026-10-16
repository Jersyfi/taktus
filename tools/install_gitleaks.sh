#!/bin/sh
# Install the pinned gitleaks into .tools/bin, the same version locally and in CI.
#
# CI's secret scan runs it through tools/scan_secrets.sh. The archive is taken from the
# project's release host and refused unless its SHA-256 is the one written here: a new version
# is a change to this file, with the digests the release publishes.
#
# POSIX sh; needs curl, tar and shasum or sha256sum.

set -eu

VERSION="8.24.3"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ROOT/.tools/bin"

case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) echo "install_gitleaks: no pinned build for $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64 | amd64) arch=x64 ;;
    arm64 | aarch64) arch=arm64 ;;
    *) echo "install_gitleaks: no pinned build for $(uname -m)" >&2; exit 1 ;;
esac

case "$os-$arch" in
    darwin-arm64) digest=b90f13bb8c90ab72083d9b0c842e39dafb82c0e5c3f872f407366b7a58909013 ;;
    darwin-x64) digest=41c44ae8ad1d6eef57d4526ad0fd67d8129eee9a856f55c2b3b9395fd3d9ec0f ;;
    linux-x64) digest=9991e0b2903da4c8f6122b5c3186448b927a5da4deef1fe45271c3793f4ee29c ;;
    linux-arm64) digest=5f2edbe1f49f7b920f9e06e90759947d3c5dfc16f752fb93aaafc17e9d14cf07 ;;
esac

if [ -x "$DEST/gitleaks" ] && "$DEST/gitleaks" version 2>/dev/null | grep -q "^$VERSION"; then
    echo "gitleaks $VERSION is in .tools/bin"
    exit 0
fi

archive="gitleaks_${VERSION}_${os}_${arch}.tar.gz"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -sSfL -o "$work/$archive" \
    "https://github.com/gitleaks/gitleaks/releases/download/v$VERSION/$archive"

if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$work/$archive" | cut -d" " -f1)
else
    actual=$(shasum -a 256 "$work/$archive" | cut -d" " -f1)
fi
if [ "$actual" != "$digest" ]; then
    echo "install_gitleaks: $archive has SHA-256 $actual, expected $digest; refused" >&2
    exit 1
fi

tar -xzf "$work/$archive" -C "$work" gitleaks
mkdir -p "$DEST"
mv "$work/gitleaks" "$DEST/gitleaks"
chmod 755 "$DEST/gitleaks"
echo "gitleaks $VERSION installed in .tools/bin"
