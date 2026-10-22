# NEED-0033 — The project's instance opens its findings intake

**Kind:** action
**Raised in:** [#558](https://github.com/Jersyfi/taktus/pull/558)
**Issue:** [#557](https://github.com/Jersyfi/taktus/issues/557)
**Needed by:** 2026-10-31
**Foreseeable since:** DEC-0217, which decided that findings reach the project through the intake of its own instance

## 1. What is needed

Four settings on the Taktus project's own instance, at its next install. They open the intake
through which the business's instance sends its findings (ADR-0118). They also keep the
instance sending its own findings, which it now does only at a level its operator sets.

- `TAKTUS_FINDINGS_INTAKE_TENANT`: the identifier of the project's tenant on the instance. Its
  owner, you, confirms every new sender once, in your channel.
- `TAKTUS_FINDINGS_LEVEL`: `automatic`, so that the instance keeps sending its own findings as
  before. `review` makes you confirm each one; `off` stops them.
- `TAKTUS_FINDINGS_CONNECTOR` stays as it is: the repository connector, which the chart sets
  with `connectors.repository.findings: true`. The intake opens issues through it, as the
  project's one app.
- `TAKTUS_FINDINGS_INTAKE_RATE`, optional: how many submissions one sender may make in an hour.
  30 by default.

## 2. Why

The business's instance sends nothing without an intake to send to. Its findings then stay on
its instance, and its operator sends them by hand. The project's instance sends its own
findings only at the level `review` or `automatic` since this release. Without the level, it
stops sending them after the install.

## 3. By when

**2026-10-31**, when the business's stage 0 is meant to start (#400).

## 4. How to provide it

1. In the instance's chart values, under `env`, set `TAKTUS_FINDINGS_INTAKE_TENANT` to the
   project's tenant and `TAKTUS_FINDINGS_LEVEL` to `automatic`. Keep
   `connectors.repository.findings: true`.
2. Install the release that carries ADR-0118, as every release is installed.
3. Tell the business's operator the intake's address: the instance's host and path prefix,
   followed by `/findings/intake`. The ingress already routes it; nothing else opens.
4. The business's operator sets `TAKTUS_FINDINGS_INTAKE` to that address, and
   `TAKTUS_FINDINGS_LEVEL` to `review` or `automatic`.
5. At the business's first finding, your channel asks you to confirm its sender. Ask the
   business's operator for the sender's identifier: `taktusctl findings` prints it below every
   finding. Answer the message that it is done only when the two match.

## 5. What it must never be

Never the tenant's identifier, the instance's host or any value of the business in this
repository, an issue or a chat with a session. The settings live in the instance's private
values only.

## 6. What happens next

The instance answers each submission of an unconfirmed sender `held`. Once you confirmed the
sender, its findings open or add to issues in this repository, labelled as the instance's
findings are. Answer in the issue with the sentence "NEED-0033: provided".

## 7. How to confirm

After the install, this made-up submission is answered 401, `forged`, by an open intake:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' \
  -d '{"key":"k","payload":"{}","signature":"s"}' "https://<host><prefix>/findings/intake"
```

A 404 says the intake is not open.
