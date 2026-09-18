#!/bin/sh
# Placed into the unit's container by the container execution adapter, and run as its
# entrypoint in front of the image's own command. It waits until the adapter has written the
# job's credentials into the memory-backed directory below, exports the ones injected as
# environment variables, removes what it read, and becomes the unit. Nothing here is a secret;
# the values arrive after the container has started and live in memory only.
set -eu
dir="${TAKTUS_CREDENTIALS_DIR:-/run/taktus/credentials}"
n=0
while [ ! -e "$dir/.ready" ]; do
    n=$((n + 1))
    if [ "$n" -gt 600 ]; then
        echo "launch: the credentials did not arrive within 60s" >&2
        exit 70
    fi
    sleep 0.1
done
if [ -d "$dir/env" ]; then
    for file in "$dir"/env/*; do
        [ -f "$file" ] || continue
        name=$(basename "$file")
        value=$(cat "$file")
        export "$name=$value"
    done
    rm -rf "$dir/env"
fi
rm -f "$dir/.ready"
exec "$@"
