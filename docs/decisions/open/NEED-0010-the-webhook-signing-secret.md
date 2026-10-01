# NEED-0010 — The webhook signing secret

**Kind:** credential
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** [#54](https://github.com/Jersyfi/taktus/issues/54)
**Needed by:** 2026-10-20
**Foreseeable since:** [#40](https://github.com/Jersyfi/taktus/pull/40), whose deployment plan deferred it to "once the ingress name exists" (`deploy/k8s/README.md` §8); raised on 2026-10-01, because ADR-0028 raises a need when it becomes foreseeable, not when it blocks

## 1. What is needed

A random secret, shared between the repository's hosting service and the deployed Taktus
instance. The hosting service signs every webhook delivery with it; the repository connector
verifies the signature and refuses every delivery it cannot verify, before reading the body
(`contracts/connector/v1` §7).

It is a shared secret, not an account: you generate it yourself, and nobody issues it.

## 2. Why

Taktus reacts to events in the repository — an issue opened, a comment, a pipeline finished —
through the webhook. Without the secret, the connector cannot tell a delivery from the hosting
service from a request anyone could send to a public address, so it refuses all of them. The
instance then keeps polling instead of reacting.

The secret can be generated now. Only the second half — setting it on the webhook — waits for
the public name (NEED-0008), because the webhook is pointed at an address under that name.

## 3. By when

**2026-10-20**, with NEED-0008, so that the deployment pull request sets up intake in one
move: the name, the webhook and the secret.

If it is not there by then: the deployment installs without intake. Nothing breaks; the
instance does not receive events and reacts only to what it polls or what is submitted with
`taktusctl`.

## 4. How to provide it

1. **Generate the secret** on your own machine, into a file readable by you alone:

   ```bash
   umask 077; openssl rand -hex 32 > <the file>
   ```

2. **Keep the file in your secret store**, next to the platform's other secrets.
3. **Once NEED-0008's name exists**, create the webhook on the repository at the hosting
   service: the address `<name><prefix>/intake/<channel>` from `deploy/k8s/README.md` §2, content
   type JSON, the events the connector declares (`src/taktus/adapters/driven/connectors/github/README.md`),
   and as its secret the content of the file. Paste it into the hosting service's form only.
4. **Give the same value to the instance** as the deployment pull request describes: a secret in
   the control plane's namespace, which the chart hands to the connector under the name the
   connector declares for intake, `REPOSITORY_WEBHOOK_SECRET`. The secret's name on your cluster
   is yours.

## 5. What it must never be

- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.
- **Never the repository token**, or any other credential reused. It is its own random value.
- **Never set on one side only.** A secret on the webhook and another, or none, on the instance
  means every delivery is refused.

Where it goes instead: your secret store, the hosting service's webhook form, and the cluster
secret the chart reads.

## 6. What happens next

Tell the session: **"NEED-0010 is provided; the secret is on the webhook and on the instance."**
The deployment pull request then switches intake on. The first delivery after that — the
hosting service sends a test event when a webhook is created — shows in the instance's log as
verified.

## 7. How to confirm

Without revealing anything: in the hosting service's webhook settings, the recent deliveries
list the test event with a success response. A delivery answered with a refusal means the two
sides hold different values; set both again from the file.
