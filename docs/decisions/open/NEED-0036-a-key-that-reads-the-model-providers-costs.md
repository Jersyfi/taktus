# NEED-0036 — A key that reads the model provider's costs

**Kind:** credential
**Raised in:** the branch `concept/package-a` (package A, built in concept mode, DEC-0222), for issue #447
**Issue:** to be opened with the label `needs-owner` when package A's pull request is opened; it serves #447
**Needed by:** 2026-11-20
**Foreseeable since:** the branch `concept/package-a`, where the model costs connector was first proven against a fake of the provider

## 1. What is needed

A key with which Taktus's own instance may read what the project's organisation spent per day at
the model provider whose costs the model costs connector reads (OpenAI). The provider calls it an
admin key. It belongs to the organisation, not to a person, and only Taktus holds it.

## 2. Why

The first condition of `1.0.0-beta` is that a stage-1 process of UC-03 runs on Taktus's own
instance against the real service (`docs/roadmap.md`, "The road to 1.0.0"). The cost watcher
(`blueprints/software-operations/processes/B-1.01-daily-cost.yaml`) reads a cloud bill; it reads
a model provider's costs in the same shape when its step `read-costs` names
`models.costs.daily`, which UC-03 B-2.01 also needs. The project spends on model providers, so
this is the real service most likely at hand. The connector acts with the credential named
`MODEL_COSTS_TOKEN`. One of this need and NEED-0035 is enough for the beta condition.

## 3. By when

**2026-11-20**, so that a cost watcher runs on the instance for a week before `0.5.0` closes.
If neither this nor NEED-0035 is there by then, the cost watcher is proven against fakes alone,
and the beta condition waits. Nothing else waits.

## 4. How to provide it

**Step 1 — the key.** In the provider's organisation settings, under *Admin keys*, create a key
named `taktus-cost-read`. The provider offers no admin key that may only read costs, so this key
must be one only Taktus holds, never shared with a person or another tool. The console shows it
once.

**Step 2 — the value.** Write the key into a file only you can read. Put it into the instance's
secret store under the parameter `MODEL_COSTS_TOKEN`: on the cluster, a Secret in the control
plane's namespace, named in the chart's `credentials` (`deploy/k8s/README.md` §2). The parameter
is described in `CREDENTIALS.md`, row *Model costs key of the requesting identity*.

```sh
kubectl --namespace "<control-plane namespace>" create secret generic "<secret name>" \
  --from-file=key="<path of the file with the key>"
```

**Step 3 — rotation.** Rotate it once a year, and at once if it may have been seen: create a new
admin key, replace the Secret's value, then delete the old key in the console.

The provider does not bill reading the costs.

## 5. What it must never be

- **Never a key a person also uses**, and never the key a coding agent works with: those are
  other credentials with other purposes (NEED-0001, NEED-0012).
- **Never in this repository**, a chat, an issue or an environment variable a process listing
  shows. The key goes into the file and the Secret, nowhere else.
- **Never named here by the deployment's own names**: the organisation's identifier, the
  Secret's name and the namespace stay in the private note.

## 6. What happens next

Write in the issue: **"NEED-0036 is provided."** The next session records it first. It then runs
the model costs connector beside the instance, adds `models.costs` to the instance's connectors,
registers the cost watcher reading `models.costs.daily` for the project's tenant at level 1,
configures its corridor, and reports the first runs.

## 7. How to confirm

Without printing the key, from a machine that reaches the provider, with the key in a file:

```sh
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  --header "Authorization: Bearer $(cat "<path of the file with the key>")" \
  "https://api.openai.com/v1/organization/costs?start_time=1761955200&limit=1"
```

It prints `200`.
