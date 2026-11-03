# NEED-0042 — A key that reads the model costs at OpenAI

**Kind:** credential
**Raised in:** the session of 2026-11-03, after the owner's answer that replaces NEED-0035 and NEED-0036
**Issue:** [#668](https://github.com/Jersyfi/taktus/issues/668)
**Needed by:** 2026-11-20
**Foreseeable since:** the owner's answer of 2026-11-03 that neither the cloud bill (NEED-0035) nor the Anthropic organisation (NEED-0036) is a source the project has

## 1. What is needed

An Admin key of the owner's organisation at OpenAI, with which Taktus's own instance reads what
the organisation spent per day from the organisation costs API (`GET /v1/organization/costs`),
and nothing else. It is kept in 1Password, in the vault `Development`, as the item
`taktus-openai-cost-read`, field `credential`, and put into the instance's secret store under
the parameter `MODEL_COSTS_TOKEN`.

## 2. Why

The first condition of `1.0.0-beta` is that a stage-1 process of UC-03 runs on Taktus's own
instance against the real service. The model cost watcher, `blueprints/software-operations/
processes/B-2.01-model-cost.yaml`, reads the capability `models.costs`, which the connector
`connectors/taktus_connectors/openai/` serves with the credential `MODEL_COSTS_TOKEN`. The two
earlier paths are closed: the project runs nothing on AWS (NEED-0035), and the owner's Anthropic
account is one for an individual, which has no Admin keys (NEED-0036).

## 3. By when

**2026-11-20**, so that the cost watcher runs on the instance for a week before `0.5.0` closes.
If it is not there by then, the beta condition stays open. Nothing else waits.

## 4. How to provide it

**Step 1 — the key.** Signed in at OpenAI's platform as the organisation's owner, create an Admin
key named `taktus-cost-read` under the organisation's settings. The platform shows it once.

**Step 2 — the vault.** Store it in 1Password, vault `Development`, as an item of the category
*API credential* titled `taktus-openai-cost-read`, the key in its field `credential`.

**Step 3 — the instance.** From 1Password into the instance's secret store, without the value
passing through a file or a screen:

```sh
op read --account "<your 1Password account>" "op://Development/taktus-openai-cost-read/credential" | ssh "<host that runs kubectl>" "kubectl --namespace <control-plane namespace> create secret generic taktus-model-costs --from-file=key=/dev/stdin"
```

The session names the private values to add: the credential `credential.model_costs_token`, and
`MODEL_COSTS_TOKEN: none` under `administration.administers`.

**Rotation:** once a year, and at once if it may have been seen: a new key into the vault item,
step 3 again with the Secret replaced, then the old key revoked at OpenAI.

## 5. What it must never be

- **Never a key that does real work elsewhere**, such as a project key that calls models.
- **Never in this repository**, a chat, an issue or a variable that a process listing shows.

## 6. What happens next

Write in the issue: **"NEED-0042 is provided."** The next session records it first, adds the
model costs connector to the instance, and runs B-2.01 against the real service.

## 7. How to confirm

A run of B-2.01 on the instance reads the costs of the last four weeks from OpenAI and records
them, and its connector passes the conformance suite against the real service.
