#!/usr/bin/env sh
# Write the two secret files the compose file reads, unless they exist: a random database
# password, and the database URL that carries it. Values never leave this directory, which git
# ignores. Run by `make up`; safe to run again — existing files are kept, so that a running
# database keeps its password.
#
# Compose mounts each file into its container with the file's own owner and mode, and the
# containers read it as their own user (uid 999), not as the host user who wrote it. A file
# only its writer may read therefore stops the instance on Linux. The directory is closed to
# every other host user instead, and the files in it are readable, which an existing install's
# files are brought to as well.
set -eu
dir="$(cd "$(dirname "$0")" && pwd)/secrets"
mkdir -p "$dir"
chmod 700 "$dir"
if [ ! -s "$dir/postgres_password" ]; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$dir/postgres_password"
    echo "secrets: wrote $dir/postgres_password"
fi
if [ ! -s "$dir/database_url" ]; then
    printf 'postgresql://taktus:%s@postgres:5432/taktus\n' "$(cat "$dir/postgres_password")" \
        > "$dir/database_url"
    echo "secrets: wrote $dir/database_url"
fi
chmod 644 "$dir/postgres_password" "$dir/database_url"
