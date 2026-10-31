#!/bin/sh
# Install the pinned vulnerability scanner (grype) and signing tool (cosign) into .tools/bin, the
# same versions locally and in the image workflow (ADR-0173).
#
# `make image-tools` runs it; `.github/workflows/images.yml` runs it before it scans or signs.
# Each file is taken from its project's release host and refused unless its SHA-256 is the one
# written here: a new version is a change to this file, with the digests its release publishes.
# No action of a third party installs either tool: what runs in the workflow is what this file
# names.
#
# POSIX sh; needs curl, tar and shasum or sha256sum.

set -eu

GRYPE_VERSION="0.120.1"
COSIGN_VERSION="3.1.3"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ROOT/.tools/bin"

case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) echo "install_image_tools: no pinned build for $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64 | amd64) arch=amd64 ;;
    arm64 | aarch64) arch=arm64 ;;
    *) echo "install_image_tools: no pinned build for $(uname -m)" >&2; exit 1 ;;
esac

case "$os-$arch" in
    darwin-amd64)
        grype_digest=5313004ccbc524c8757521dc3913f1edf4309f56bef06a2fb2d0c0eeade7cc62
        cosign_digest=2347488e5d5b25336644024dfeca5601b190e91197a71a917bda44744aff106c ;;
    darwin-arm64)
        grype_digest=cf97957fa467d25575ec2cc3228289f391ea51cf88b9cffc5f83dc03d4cbc732
        cosign_digest=5cf948c2f4dfe59687bdd0b8523709067383e03982cc543475c8a7dc70e92a76 ;;
    linux-amd64)
        grype_digest=0a9ee97ef5ae2ee953b0a80098105052e846cdbe319a57d808b519c33cd1343d
        cosign_digest=4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71 ;;
    linux-arm64)
        grype_digest=29f47391dc283aa79fcc38e65224cd61f64dec0ecfd0db7074128ebf8ff23514
        cosign_digest=c5d324e091826b0d7a78eb16fef316450b4eb9aaec045611c08ba06f5e73220a ;;
esac

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d" " -f1
    else
        shasum -a 256 "$1" | cut -d" " -f1
    fi
}

fetch() { # url file expected-digest
    curl -sSfL -o "$2" "$1"
    actual=$(sha256 "$2")
    if [ "$actual" != "$3" ]; then
        echo "install_image_tools: $(basename "$2") has SHA-256 $actual, expected $3; refused" >&2
        exit 1
    fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$DEST"

if [ -x "$DEST/grype" ] && "$DEST/grype" version 2>/dev/null | grep -Eq "^Version: +$GRYPE_VERSION$"; then
    echo "grype $GRYPE_VERSION is in .tools/bin"
else
    archive="grype_${GRYPE_VERSION}_${os}_${arch}.tar.gz"
    fetch "https://github.com/anchore/grype/releases/download/v$GRYPE_VERSION/$archive" \
        "$work/$archive" "$grype_digest"
    tar -xzf "$work/$archive" -C "$work" grype
    mv "$work/grype" "$DEST/grype"
    chmod 755 "$DEST/grype"
    echo "grype $GRYPE_VERSION installed in .tools/bin"
fi

if [ -x "$DEST/cosign" ] && "$DEST/cosign" version 2>/dev/null | grep -Eq "^GitVersion: +v$COSIGN_VERSION$"; then
    echo "cosign $COSIGN_VERSION is in .tools/bin"
else
    binary="cosign-$os-$arch"
    fetch "https://github.com/sigstore/cosign/releases/download/v$COSIGN_VERSION/$binary" \
        "$work/$binary" "$cosign_digest"
    mv "$work/$binary" "$DEST/cosign"
    chmod 755 "$DEST/cosign"
    echo "cosign $COSIGN_VERSION installed in .tools/bin"
fi
