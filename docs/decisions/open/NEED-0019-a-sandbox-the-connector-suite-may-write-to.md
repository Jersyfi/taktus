# NEED-0019 — A sandbox the connector suite may write to

**Kind:** access
**Raised in:** [#162](https://github.com/Jersyfi/taktus/pull/162), for issue #93
**Issue:** [#161](https://github.com/Jersyfi/taktus/issues/161)
**Needed by:** 2026-10-31
**Owner's answer:** 2026-10-10: the session creates the repository and its issue and tells the owner when the app's installation is to be extended, which stays the owner's.
**Foreseeable since:** [#162](https://github.com/Jersyfi/taktus/pull/162), where the instance learned to run an adapter's conformance suite itself and record it

## 1. What is needed

A repository on the repository service that exists for one purpose: Taktus's instance runs the
repository connector's conformance suite against it. The suite is a program that checks whether
an adapter keeps its contract. For a connector it really writes: it opens issues, pull requests,
comments and branches, twice each, to show that a repeat with the same key creates nothing new.
It must therefore never write into this repository, the one Taktus maintains. What is needed:

1. **A private repository**, empty but for one issue (number 1) and a branch `main`. The suite
   reads issue 1 and opens its pull requests against `main`.
2. **Taktus's own app** (NEED-0013) **installed on it**, with the permissions it has on this
   repository and no others.
3. **Its name**, as `owner/name`, in the instance's private configuration, where the operator
   keeps the names of the platform (never in this repository).

## 2. Why

An adapter is *verified* when its contract's conformance suite and the removal test both passed.
From autonomy level 3 a step runs only on a *verified* adapter. Taktus's own processes P-01, P-02
and P-03 run at level 3 and 4, and every one of their steps on the repository connector halts
until that connector is *verified* on the instance (ADR-0039).

Since issue #93 the instance runs the suite itself and records the outcome in the adapter's
maturity (`taktusctl conformance record connector.<label>`, ADR-0044). Against a stand-in for the
service that is proven. Against the real service on the instance it needs a target the suite may
write to. That run belongs to starting P-01 to P-03 on the instance (issue #87), which is part of
the milestone `0.2.0`.

The repository connector serves one repository, the one it is started for. So on the instance the
suite needs a connector started for the sandbox. How a pass there stands for the connector that
serves this repository is settled in issue #87. The sandbox is needed either way.

## 3. By when

**2026-10-31**, so that issue #87 can run the suite on the instance when it starts.

If it is not there by then: the repository connector on the instance cannot be tested against the
real service without writing into this repository. It stays *experimental*, and every step of
P-01 to P-03 on it halts at level 3. Nothing else waits.

## 4. How to provide it

**Step 1 — the repository.** At the repository service, create a new **private** repository
under your account. Name it as you like; its name never enters this repository. Initialise it
with a README, so that `main` exists. Then open one issue in it, with any title: it becomes issue
number 1, which the suite reads.

```sh
gh repo create "<owner>/<name>" --private --add-readme
gh issue create --repo "<owner>/<name>" --title "Read by the conformance suite" --body "Leave open."
```

**Step 2 — the app.** In the settings of Taktus's app (NEED-0013), under *Install App*, add the
new repository to the existing installation: *Only select repositories*, then this repository,
the scratch repository of the live test, and the new one. The app's permissions stay as they are.

**Step 3 — the name.** Write `owner/name` into the private note where the instance's platform
names are kept, under "conformance sandbox". It is not a secret, but it is a deployment's own
name and stays out of this public repository (CLAUDE.md §9).

## 5. What it must never be

- **Never this repository**, and never the scratch repository of the live test: the suite's
  records there would mix with what P-01 to P-03 read and with what the live test counts.
- **Never public.** The suite writes recorded payloads and branch names into it; nobody needs to
  see them.
- **Never a token of yours.** The instance acts as the app (ADR-0033); no personal token is
  created for this.
- **Its name never in this repository**, nor in an issue, a pull request or a chat.

## 6. What happens next

Write in the issue: **"NEED-0019 is provided."** The next session records it first. The sandbox
is then used when issue #87 starts P-01 to P-03 on the instance: a connector started for the
sandbox, the scenario pointed at it, and `taktusctl conformance record` run once.

## 7. How to confirm

Without revealing anything, from your workstation:

```sh
gh repo view "<owner>/<name>" --json visibility,defaultBranchRef --jq '.visibility, .defaultBranchRef.name'
gh issue view 1 --repo "<owner>/<name>" --json state --jq .state
```

The first prints `PRIVATE` and `main`; the second prints `OPEN`. In the app's settings, the
installation lists three repositories.
