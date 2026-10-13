# NEED-0026 — The ruleset stops requiring an up-to-date branch

**Kind:** action
**Raised in:** the pull request that records DEC-0194, for issue #391
**Issue:** [#398](https://github.com/Jersyfi/taktus/issues/398)
**Needed by:** 2026-10-31
**Foreseeable since:** DEC-0194, where the owner accepted that a pull request merges without catching up with `main` once a guard keeps `main` green

## 1. What is needed

One setting changed in the repository's ruleset on GitHub. Today a pull request may merge only when
its branch contains the newest `main` ("Require branches to be up to date before merging"). The
setting is to be switched off. Everything else in the ruleset stays.

Only the owner can change the ruleset. No session and no Taktus process holds that right, and
none should.

## 2. Why

44 % of the pull requests' CI minutes went to re-checking a branch only because it had been
brought up to date. A replay of the last 100 merges found that no merge would have produced a
broken `main` without it (`docs/research/2026-10-13-ci-review.md` §2). ADR-0096 §5 replaces the
setting by a guard: no pull request merges while `main` is red, and every commit on `main` is
checked in full.

## 3. By when

**When issue #391 is merged**, and by 2026-10-31 at the latest. Switching it off before the guard
exists would let pull requests merge onto a red `main`. Switching it off later only costs time.

If it is not done: nothing breaks, and pull requests keep catching up as today.

## 4. How to provide it

1. Open the repository on GitHub: **Settings → Rules → Rulesets → main**.
2. Under **Require status checks to pass**, clear **Require branches to be up to date before
   merging**. Leave the required check `gates` as it is.
3. Save.

## 5. What it must never be

Never a bypass of the ruleset for a person or an app, and never the removal of the required
check `gates`. Only the one setting above changes. No value is involved, and none is sent to a
session.

## 6. What happens next

Answer in the issue: "NEED-0026: done." The next session reads the ruleset and records the
need as provided. From then on a pull request merges without catching up, and the guard of #391
holds every merge while `main` is red.

## 7. How to confirm

```sh
gh api repos/Jersyfi/taktus/rulesets/23481185 --jq '.rules[] | select(.type=="required_status_checks") | .parameters.strict_required_status_checks_policy'
```

It prints `false`.
