# NEED-0035 — A read-only key for the cloud bill

**Kind:** credential
**Raised in:** the branch `concept/package-a` (package A, built in concept mode, DEC-0222), for issue #447
**Issue:** to be opened with the label `needs-owner` when package A's pull request is opened; it serves #447
**Needed by:** 2026-11-20
**Foreseeable since:** the branch `concept/package-a`, where the cost watcher (UC-03 B-1.01) first ran against a fake of the cloud provider's billing

## 1. What is needed

A key with which Taktus's own instance may read the daily costs of one cloud account at the
cloud provider whose billing the cost watcher reads (AWS), and do nothing else. The key is a
pair: an access key id and a secret access key. It belongs to a user or role that exists only
for this, and whose only right is to read the cost figures.

## 2. Why

The first condition of `1.0.0-beta` is that a stage-1 process of UC-03 runs on Taktus's own
instance against the real service, through connectors that pass the conformance suite
(`docs/roadmap.md`, "The road to 1.0.0"). The cost watcher, `blueprints/software-operations/
processes/B-1.01-daily-cost.yaml`, is built for that. Its step `read-costs` calls the operation
`billing.costs.daily` of the cloud billing connector, and the connector acts with the
credential named `BILLING_KEY`. Without it the process is proven against a fake of the
provider only, and the beta condition stays open.

NEED-0036 asks for the key that reads the model provider's costs, which the model cost watcher
(B-2.01) reads in the same shape. The project already holds that account, so NEED-0036 is the
recommended path; one of the two is enough for the beta condition. Where the project keeps no
account at this cloud provider, say so, and this need is closed.

## 3. By when

**2026-11-20**, so that the cost watcher runs on the instance for a week before `0.5.0` closes.
If it is not there by then, the cost watcher is proven against the fake alone, and the beta
condition waits for this or for NEED-0036. Nothing else waits.

## 4. How to provide it

**Step 1 — the right, and no more.** In the provider's identity console (IAM), create a policy
with exactly this statement, and name it `taktus-cost-read`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "ce:GetCostAndUsage", "Resource": "*" }
  ]
}
```

Where the account is part of an organisation and the costs of every member account are to be
watched, do this in the organisation's management account; otherwise in the account itself.

**Step 2 — the identity.** Create a user `taktus-cost-watcher` with no console access, and
attach only the policy `taktus-cost-read`. Under *Security credentials → Access keys*, create an
access key for an application running outside the provider. The console shows the secret once.

**Step 3 — the value.** Join the two halves as `<access key id>:<secret access key>` and write
that into a file only you can read. Put it into the instance's secret store under the parameter
`BILLING_KEY`: on the cluster, a Secret in the control plane's namespace, named in the chart's
`credentials` (`deploy/k8s/README.md` §2). The parameter is described in `CREDENTIALS.md`, row
*Cloud billing key of the requesting identity*.

```sh
kubectl --namespace "<control-plane namespace>" create secret generic "<secret name>" \
  --from-file=key="<path of the file with id:secret>"
```

**Step 4 — rotation.** Rotate the key once a year, and at once if it may have been seen: create
a second access key for the same user, replace the Secret's value, then deactivate and delete
the first key.

Each request this key makes is billed by the provider, at about one cent. The cost watcher makes
one a day.

## 5. What it must never be

- **Never a key with more than `ce:GetCostAndUsage`**, never an administrator's key, never the
  account's root key, and never your own.
- **Never in this repository**, a chat, an issue or an environment variable a process listing
  shows. The pair goes into the file and the Secret, nowhere else.
- **Never named here by the deployment's own names**: the account's number, the Secret's name
  and the namespace stay in the private note.

## 6. What happens next

Write in the issue: **"NEED-0035 is provided."** The next session records it first. It then runs
the cloud billing connector beside the instance, adds `billing.costs` to the instance's
connectors, registers B-1.01 for the project's tenant at level 1, configures its corridor
(`taktusctl signal configure`, as the bundle's header shows), and reports the first runs.

## 7. How to confirm

Without printing the key, from a machine with the provider's command line and the pair in the
usual profile of a scratch configuration:

```sh
aws ce get-cost-and-usage --time-period Start=2026-11-01,End=2026-11-02 \
  --granularity DAILY --metrics UnblendedCost --query 'length(ResultsByTime)'
```

It prints `1`. The same profile running `aws iam list-users` is refused with `AccessDenied`.
