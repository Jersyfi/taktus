# NEED-0024 — The coding agents' keys on the instance

**Kind:** credential
**Raised in:** the pull request that raises it, after #222 let an instance run several workers
**Issue:** [#226](https://github.com/Jersyfi/taktus/issues/226)
**Needed by:** before #87, which starts P-01 to P-03 on the instance
**Foreseeable since:** [#222](https://github.com/Jersyfi/taktus/pull/222), whose report named it: NEED-0001 and NEED-0005 put the first agent's key on the owner's workstation, NEED-0012 and NEED-0022 put keys in the environment `live` for tests, and nothing puts a key where the installed instance runs real work

## 1. What is needed

For each coding agent the instance runs — the first (`workers/claudecode/`) and, once #208 has
passed its live test, the second (`workers/codex/`) — an API key **of its own for the instance's
real work**, in a project of that vendor's platform with a hard monthly spend limit you set. Each
key is placed in a file on your workstation, readable by you alone, beside the other credential
files, and from there into one secret in the control plane's namespace on the cluster.

## 2. Why

P-03, the process that turns a ready issue into a pull request, has one step a coding worker
does. On the installed instance the coding worker runs as a job in the cluster (ADR-0034,
`deploy/k8s/README.md` §7). The job receives exactly the credentials its step names, from a
secret the chart mounts (`credentials[]`, parameter `worker.<worker>.credential.CODING_AGENT_API_KEY`,
ADR-0078). Without a key there, every P-03 run on the instance stops at that step, and #87 —
Taktus maintaining its own repository — cannot be shown.

The keys of the workstation and of the environment `live` must not be reused: a key that does
real work must be revocable without stopping the tests, and what the instance spends must be
visible and limited on its own (DEC-0048, DEC-0058).

## 3. By when

Before #87 is taken up, which needs the instance installed (#66) first. If it is not there:
nothing breaks; P-03 on the instance halts at its coding step, naming the missing credential, and
a person can do that step by hand (#90).

## 4. How to provide it

1. **Create a project for the instance** on each vendor's platform, separate from the projects
   for live tests and from your own use, named for what it is for — "taktus instance".
2. **Set a monthly budget with a hard limit** on each project. Its amount is yours (M3.10); it is
   the backstop behind every run's own budget (ADR-0005). For P-03 on this repository, USD 30 a
   month is a starting point: a run that opens one pull request costs cents to a few dollars.
3. **Create an API key in each project**, restricted to it, named "taktus instance, coding".
4. **Save each key into a file** on your workstation, readable by you alone, beside the other
   credential files: `instance-coding-agent-api-key` for the first agent and
   `instance-second-coding-agent-api-key` for the second. Never paste a key anywhere else.
5. **Say so in the issue.** The session — on your permission to act on the cluster with the
   deployment identity, which is still to be given (#66) — or you create the secret
   `taktus-coding-agents` in the control plane's namespace from those files, without printing
   them, and names it in the instance's private values. The first key is enough to start; the
   second follows when #208 has passed.

## 5. What it must never be

- **Never the key of NEED-0001, NEED-0005, NEED-0012 or NEED-0022.** Each of those has its own
  purpose and its own limit.
- **Never a key without a hard monthly limit** on its project.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. It
  goes from the vendor's console into its file, and from the file into the cluster's secret.
- **Never a subscription login.** The instance runs unattended; a login renews itself in a file
  the worker does not keep.

## 6. What happens next

Write in this issue: **"NEED-0024 is provided."** The next session records it first, creates or
checks the secret, adds it to the instance's private values (`credentials[]` per worker), and
upgrades the install. #87 can then run P-03 on the instance.

## 7. How to confirm

Without revealing anything: each vendor's console lists the project with its key, no usage yet,
and the budget you set. On the cluster, the secret `taktus-coding-agents` in the control plane's
namespace lists its key names — read with `-o jsonpath='{.data}'` and only the names printed — and
no value is shown. After the first P-03 run on the instance, the project shows
that run's usage and nothing else.
