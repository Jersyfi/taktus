# ADR-0011 — Process bundles, optionally mirrored to Git

**Status:** accepted

## Context
Required: define processes inside Taktus (no external system does it), see them transparently,
change them in dialogue, and have a change history with rollback. Git would give history, diff,
review and rollback for free — and would be an absurd barrier for a private user without a
repository, and would introduce a second source of truth.

## Decision
**The bundle is the truth**: definition, prompts, skills, connector capabilities, governance rules
and value criteria as one versioned package. The database holds the pointer to the active version
and the run data. Mirroring to Git is **enabled per process** and is a projection, not a second
source.

## Alternatives
- **Database only** — history yes, but no review and no diff in the familiar tool.
- **Git only** — review yes, unusable for anyone without a repository.

## Consequences
- The same coupled/decoupled logic used for process control, applied to storage.
- For the Taktus project itself: mirroring on. A process change becomes a reviewable pull request.
- The open bundle format is **not** pulled forward: the format exists internally from `0.3.0`; the
  open specification stays after `1.0.0`.
