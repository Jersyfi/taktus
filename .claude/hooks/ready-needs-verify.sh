#!/bin/sh
# A session hook: `gh pr ready` is refused unless `make verify` stamped the head that was pushed
# (ADR-0096 §4, #390).
#
# Installed by .claude/settings.json as a PreToolUse hook on Bash. It reads the call as JSON on
# standard input and lets everything through except a command that marks a pull request ready.
# For that, the stamp `.git/taktus-verified`, which tools/verify.sh writes, must name the
# current head, and the head must be what the branch's upstream holds: CI starts when the pull
# request is ready, and what it then checks is what was verified. Exit 2 refuses the call and
# says why; Claude Code shows the message to the session.
#
# Where it ends: it checks the branch checked out here. `gh pr ready <number>` for a pull request
# of another branch is judged by this branch's stamp. `gh pr ready --undo` turns a pull request
# back into a draft and is let through.
#
# POSIX sh; needs python3 and git.

set -eu

command=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))')
case "$command" in
    *"gh pr ready"*) ;;
    *) exit 0 ;;
esac
case "$command" in
    *--undo*) exit 0 ;;
esac

head=$(git rev-parse HEAD)
stamp="$(git rev-parse --git-dir)/taktus-verified"
if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$head" ]; then
    echo "Refused: run \`make verify\` on a clean tree first; its stamp must name the head $head (ADR-0096 §4)." >&2
    exit 2
fi
upstream=$(git rev-parse '@{u}' 2>/dev/null || echo none)
if [ "$upstream" != "$head" ]; then
    echo "Refused: push first; the branch's upstream is at $upstream, the verified head is $head." >&2
    exit 2
fi
exit 0
