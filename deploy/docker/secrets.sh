#!/usr/bin/env sh
# Write the two secret files the compose file reads, unless they exist: a random database
# password, and the database URL that carries it. Values never leave this directory, which git
# ignores. Run by `make up`; safe to run again — existing files are kept, so that a running
# database keeps its password.
set -eu
dir="$(cd "$(dirname "$0")" && pwd)/secrets"
mkdir -p "$dir"
if [ ! -s "$dir/postgres_password" ]; then
    umask 077
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$dir/postgres_password"
    echo "secrets: wrote $dir/postgres_password"
fi
if [ ! -s "$dir/database_url" ]; then
    umask 077
    printf 'postgresql://taktus:%s@postgres:5432/taktus\n' "$(cat "$dir/postgres_password")" \
        > "$dir/database_url"
    echo "secrets: wrote $dir/database_url"
fi
