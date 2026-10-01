#!/bin/sh
# Placed into the unit's container by the container execution adapter, and run as its
# entrypoint in front of the image's own command. It waits until the adapter has written the
# job's credentials into the memory-backed directory below, exports the ones injected as
# environment variables, removes what it read, and runs the unit as its child. Nothing here is a
# secret; the values arrive after the container has started and live in memory only.
#
# It stays in front of the unit, rather than becoming it, for one reason: to read the kernel's
# own record of an out-of-memory kill after the unit has died. The engine's `OOMKilled` flag is
# set by a separate event that may arrive after the exit, or not at all when the cgroup goes
# with the process (issue #29); the cgroup's `oom_kill` counter is written by the kernel at the
# kill. When the unit ends killed and the counter is above zero, one line says so on standard
# error, and the adapter reads it from the unit's log. Signals are forwarded to the unit, and
# the unit's exit status is this script's.
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

# The cgroup's count of out-of-memory kills: v2's memory.events, else v1's memory.oom_control.
# Read with the shell alone, so that an image without tools still has it.
oom_kills() {
    for record in /sys/fs/cgroup/memory.events /sys/fs/cgroup/memory/memory.oom_control; do
        [ -r "$record" ] || continue
        while read -r key value; do
            if [ "$key" = oom_kill ]; then
                echo "$value"
                return
            fi
        done < "$record"
        return
    done
}

before=$(oom_kills)
"$@" &
unit=$!
trap 'kill -TERM "$unit" 2>/dev/null' TERM
trap 'kill -INT "$unit" 2>/dev/null' INT
trap 'kill -HUP "$unit" 2>/dev/null' HUP
set +e
status=0
while :; do
    wait "$unit"
    status=$?
    kill -0 "$unit" 2>/dev/null || break
done
after=$(oom_kills)
if [ "$status" -eq 137 ] && [ "${after:-0}" -gt "${before:-0}" ]; then
    echo "taktus-launch: oom_kill ${after} — the kernel killed the unit for exceeding its memory limit" >&2
fi
exit "$status"
