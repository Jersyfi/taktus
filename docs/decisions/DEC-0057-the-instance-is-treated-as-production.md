# DEC-0057 — The instance is treated as production

**Category:** NON-BLOCKING
**Raised in:** the owner's answers of 2026-10-08 to the session's proposals for NEED-0007 to NEED-0012; recorded in [#97](https://github.com/Jersyfi/taktus/pull/97)
**Issue:** none; the owner answered in conversation before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-08
**Written after the answer:** the owner answered in conversation on 2026-10-08; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The deployment needs six things only the owner can provide (NEED-0007 to NEED-0012). The session
proposed, for each, the choice it thought best for Taktus. The owner answered. Most answers fix
how a need is provided. One fixes how the whole deployment is to be treated: the cluster Taktus
runs on had been called an integration server, and DEC-0023 placed Taktus there.

## 2. Why you are being asked

What the deployed instance is for, and what is published under the project's domain, are the
owner's (M3.7); how a need is provided is the owner's act (M2.5).

**Sources checked:** the vision (principle 12, production-ready), the ADRs (ADR-0013 on business
criticality, ADR-0025 on where an instance runs), both anchor pages (M2.5, M3.7) and the register
(DEC-0023, DEC-0032, DEC-0033). They place Taktus on the cluster; none says whether that instance
is held to production standards.

## 3. What you must decide

How the deployed instance is treated, and how the open needs are provided.

## 4. What you need to know to decide

- **Production** here means: what runs there is relied on. Taktus manages itself on it and steers
  the operation, so a failure of the instance is a failure of the operation.
- The proposals were: a long-lived token for the deployment, kept on the owner's workstation; a
  subdomain of the project's domain; an object store in the EU with object lock; the webhook
  secret generated now; a scratch repository for the connector's live test; a workspace of its own
  with a small monthly limit for the coding agent's live test.

## 5. Options

### Option A — production, and the needs as answered (recommended)

- **Meaning:** see the outcome.
- **Consequence:** the instance holds real work only once its backup and restore exist; certificate
  and naming follow production practice.
- **Effort:** the needs as answered.
- **Reversibility:** cheap.
- **Why recommended:** the owner's answer, below.

### Option B — an integration environment

- **Meaning:** the instance is a test bed, and failures there are tolerated.
- **Consequence:** contradicts what the instance does: it steers the operation.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0057: Option A." or "DEC-0057: Option B."

## Outcome

**Decided:** 2026-10-08
**Answer:** the owner's, in conversation:
- **The instance is production.** The cluster is production from Taktus's point of view: Taktus
  manages itself there and steers the operation, so it is treated as a production environment.
- **NEED-0007:** the proposal accepted — a long-lived token of a namespaced deployment account,
  kept on the owner's workstation, not in CI. The session fetches the token from the server
  itself and creates the namespaces as it judges right. What it set up, and whatever must be
  kept and does not belong in this repository, goes into a note beside the owner's credential
  files.
- **NEED-0008:** not `int.taktus.eu`, but a short, playful name that says Taktus manages itself
  and the AI takes the lead; the owner creates the DNS records. The certificates are the
  session's to arrange on the server. Once Taktus manages itself, a wiki is connected for the
  documentation; the session says what the owner is to create.
- **NEED-0009:** the owner provides the backup destination at Hetzner; the session says exactly
  what it needs.
- **NEED-0010:** the session says exactly what it needs.
- **NEED-0011:** the owner asked for more context before deciding.
- **NEED-0012:** a workspace of its own already exists at the provider, with a budget of USD 50.
- **DEC-0053:** Option A.
**Reasoning given:** Taktus manages itself on that cluster and steers the operation; it must be
treated like a production environment.
**Recorded in:** [#97](https://github.com/Jersyfi/taktus/pull/97): the open needs carry what
was answered; the note on the platform is outside the repository, as the owner asked.
