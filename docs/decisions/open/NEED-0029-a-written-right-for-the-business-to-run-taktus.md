# NEED-0029 — A written right for the business to run Taktus

**Kind:** action
**Raised in:** [#450](https://github.com/Jersyfi/taktus/pull/450)
**Issue:** [#444](https://github.com/Jersyfi/taktus/issues/444)
**Needed by:** 2026-10-31
**Foreseeable since:** DEC-0201, where the owner decided that the business hosts Taktus itself

## 1. What is needed

Your written permission for the business to install and run Taktus for its own operation.
Taktus's repository is public, but its rights are all reserved until the licence is decided
(ADR-0012, DEC-0044). Public does not mean that anyone may use it. Without your permission the
business has no right to run it.

## 2. Why

The business is the second tenant and hosts its own instance (DEC-0199, DEC-0201). Stage 0, #400,
starts with its install (#443). It cannot start lawfully before the permission exists.

## 3. By when

**2026-10-31**, when stage 0 is meant to start. Without it, #400 waits. The licence itself keeps
its timing (DEC-0044) and is not needed for this.

## 4. How to provide it

1. Give the business a short written permission, for example by mail or as a signed page. It
   should say at least: the business may install and run Taktus for its own operation; for how
   long, for example until the licence is decided; that it may not pass Taktus on; and what
   happens to its feedback and findings, namely that the project may use them to improve Taktus.
2. Whether to have a lawyer read it is your decision. A session gives no legal advice.
3. Keep a copy outside the repository, in `~/Dev/taktus-private/`.
4. Answer in the issue with the sentence "NEED-0029: granted".

## 5. What it must never be

Never the permission's text, the business's name or the date it was signed in this repository,
an issue or a log. The repository records only that it exists.

## 6. What happens next

Once the issue says "NEED-0029: granted", #400 is no longer blocked by it.

## 7. How to confirm

```bash
ls ~/Dev/taktus-private/ | grep -ci permission
```

The command prints a count greater than zero once the copy is in place.
