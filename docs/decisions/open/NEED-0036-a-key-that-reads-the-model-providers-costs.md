# NEED-0036 — A key that reads the model provider's costs

**Kind:** credential
**Raised in:** the branch `concept/package-a` (package A, built in concept mode, DEC-0222), for issue #447
**Issue:** [#637](https://github.com/Jersyfi/taktus/issues/637)
**Needed by:** 2026-11-20
**Foreseeable since:** the branch `concept/package-a`, where the model cost watcher (UC-03 B-2.01) first ran against a fake of the provider's cost report

## 1. What is needed

An Admin API key of the project's organisation at Anthropic, the model provider the project's
own instance uses. With it, Taktus reads what the organisation spent per day from the
provider's cost report, and nothing else. The key belongs to the organisation, not to a
person, and only Taktus holds it.

This is the recommended path to the first beta condition, because the account already exists.
NEED-0035, a key for a cloud bill, is the other path; one of the two is enough.

## 2. Why

The first condition of `1.0.0-beta` is that a stage-1 process of UC-03 runs on Taktus's own
instance against the real service, through connectors that pass the conformance suite
(`docs/roadmap.md`, "The road to 1.0.0"). The model cost watcher,
`blueprints/software-operations/processes/B-2.01-model-cost.yaml`, is built for that. Its step
`read-costs` calls the operation `models.costs.daily` of the model costs connector over the
cost report (`src/taktus/adapters/driven/connectors/anthropic/`). That connector acts with the
credential named `MODEL_COSTS_TOKEN`. Without it the process is proven against a fake of the
provider only, and the beta condition stays open.

## 3. By when

**2026-11-20**, so that the model cost watcher runs on the instance for a week before `0.5.0`
closes. If it is not there by then, the cost watchers are proven against fakes alone, and the
beta condition waits for this or for NEED-0035. Nothing else waits.

## 4. How to provide it

**Step 1 — the key.** Sign in to the provider's console as an administrator of the
organisation. Under *Settings → Admin keys*, create a key named `taktus-cost-read`. The console
shows it once.

The provider offers no read-only admin key: every Admin API key may also administer the
organisation, its members, workspaces and keys. The scope is therefore held by who holds it.
This key is used by Taktus alone, never by a person or another tool, and the connector only
ever calls the cost report with it.

**Step 2 — the value.** Write the key into a file only you can read. Put it into the instance's
secret store under the parameter `MODEL_COSTS_TOKEN`: on the cluster, a Secret in the control
plane's namespace, named in the chart's `credentials` (`deploy/k8s/README.md` §2). The parameter
is described in `CREDENTIALS.md`, row *Model costs key of the requesting identity*.

```sh
kubectl --namespace "<control-plane namespace>" create secret generic "<secret name>" \
  --from-file=key="<path of the file with the key>"
```

Where the instance names its platform (`administration.platform`), declare the parameter as
administering none, `MODEL_COSTS_TOKEN: none` under `administration.administers`: it
administers the model provider's organisation, not the platform Taktus runs on.

**Step 3 — rotation.** Rotate it once a year, and at once if it may have been seen: create a new
admin key, replace the Secret's value, then delete the old key in the console. The connector
reads the file at every call, so nothing restarts.

The provider does not bill reading the cost report.

## 5. What it must never be

- **Never a key a person also uses**, and never the API key the instance's models or a coding
  agent work with. Those are other credentials with other purposes; an ordinary API key cannot
  read the cost report anyway.
- **Never in this repository**, a chat, an issue or an environment variable a process listing
  shows. The key goes into the file and the Secret, nowhere else.
- **Never named here by the deployment's own names**: the organisation's identifier, the
  Secret's name and the namespace stay in the private note.

## 6. What happens next

Write in the issue: **"NEED-0036 is provided."** The next session records it first. It then runs
the model costs connector over the cost report beside the instance, adds `models.costs` to the
instance's connectors, registers B-2.01 for the project's tenant, configures its corridor
(`taktusctl signal configure`, as the bundle's header shows), and reports the first runs.

## 7. How to confirm

Without printing the key, from a machine that reaches the provider, with the key in a file:

```sh
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  --header "x-api-key: $(cat "<path of the file with the key>")" \
  --header "anthropic-version: 2023-06-01" \
  "https://api.anthropic.com/v1/organizations/cost_report?starting_at=2026-11-01T00:00:00Z&limit=1"
```

It prints `200`.
