# ADR-0040 — A channel account is linked by the person who holds it

**Status:** accepted

## Context
Nothing executes without an identity (control-plane.md §2). Until now one configured operator
identity per tenant stood in for the identity component: `TAKTUS_PROVISIONAL_IDENTITY`
(DEC-0013). Every sender of every channel resolved to the tenant's operator. A comment by a
stranger on a public issue, once completed into a command, acted with the operator's rights.

UC-1.7 asks for the real thing (issue #82). A sender's account on a channel maps to exactly one
identity. The mapping is made once, by the person in their Taktus account or by the
organisation's identity source. An unknown sender gets a question or an offer to register,
never an execution. Every link and every removal of a link is in the ledger. The identity and
the organisational path are set by the identity component, never by the connector.

Three things UC-1.7 needs did not exist. Taktus had no account a person could prove: the
control plane's surface authenticated nobody. Taktus could not say anything in a channel: the
connector contract had no operation that answers at a reply address (UC-1.1 says so). And a
scheduled run acted as the provisional operator, which now goes.

## Decision

### 1. Identities, links and link codes belong to the identity component
An **identity** lives in one tenant and carries its organisational path, which starts at the
tenant. A **channel link** maps one account on one channel to one identity. Its identifier is
derived from the channel and the account, so that an account can have one link record and no
second one beside it. A link is checked against every tenant the instance serves before it is
made. A revoked link stays, marked revoked; the account is from an unknown sender again. The
component serves the identity port; nothing else maps a sender, and no connector holds the
mapping.

### 2. A person proves their identity with an account key
An administrator adds an identity with `taktusctl identity add`. The command prints the
identity's **account key** once, for the person; only its digest is kept. `taktusctl identity
key` issues a new key, and the old one stops working. The key goes in `Authorization: Bearer`
on the control plane's surface. It is the smallest proof of a Taktus account that UC-1.7 needs,
and it sits behind one method of the component (`authenticate`), so that sign-in through the
organisation's own identity provider can replace it without touching the links.

### 3. A link is made by a code the person creates and writes from the account
With their key, the person creates a **link code** for one channel
(`POST /identity/link-codes`). The code is single-use, valid for 30 minutes, and kept only as a
digest. The person writes it in the channel from the account to be linked. The intake does not
place the sender, finds the code in what they wrote, and links the account to the identity that
created the code. Creating the code proves the identity; writing it proves the account. The
message that carried it is not a command. A matching name, address or anything else in a
message links nothing.

### 4. The organisation's identity source is a port
`IdentitySource` answers, for an account on a channel, the identity and path the
organisation's source maps it to, or nothing. The component asks it for an account it has no
link for, and records what it answers as a link of origin `source`. An adapter for a
particular source is a connector of its own.

### 5. An unknown sender is answered in the channel, by Taktus itself
A sender the component cannot place is offered how to link the account. When what they wrote
linked it, they are told so. The event is kept nowhere. The answer is said through the
operation `<channel>.reply` that the channel's connector may declare (`contracts/connector/v1`
§7): input `address`, `thread` and `text`. Taktus says it as itself (ADR-0033), with the
credential the connector declares for actions. Its idempotency key is derived from the
delivery, so a redelivered event is answered once. The reference connector declares
`channel.repo.reply` as a comment on the issue or pull request.

### 6. The command line and the scheduler name an identity the component knows
`taktusctl run` and `submit` take `--identity` (or `TAKTUS_IDENTITY`). The identity must exist
in the tenant; the component supplies its path. The command line authenticates by holding the
instance's state: whoever can run it against the database is the instance's administrator.
Registering a version records the identity that registered it on the process
(`activated_by`). A schedule trigger acts for that identity, as the component places it when
the trigger fires (ADR-0035 §6, amended). The scheduler is not a sender, and a time trigger was
commissioned by whoever made the version active.

### 7. The ledger
`identity.created`, `identity.key_issued`, `identity.linked` (outcome `confirmed` or `source`)
and `identity.unlinked` (outcome `revoked`), each in the transaction of the change. An entry
carries the tenant, the acting identity where there is one, and the digest of what changed.
It never carries an account, a code or a key (ADR-0006).

## Alternatives
- **Keep the provisional identity as a fallback for unlinked senders.** DEC-0013 already
  refused it: a fallback that acts as the operator is the hole UC-1.7 closes.
- **A code shown in the channel to the unknown sender, confirmed in the account.** On a public
  channel everybody sees the code. Whoever confirms it first links somebody else's account to
  their identity. A code created in the account and written from the account is only ever seen
  in the channel after it was used.
- **Link by matching the channel's display name or e-mail address to an identity.** UC-1.7
  forbids it: an address can be set by anybody, and a name is not unique.
- **Sign-in through an external identity provider now.** It is the organisation's identity
  source of UC-10.2 and a connector of its own. The account key is enough to prove an account
  today and leaves the provider's place open.
- **Let a scheduled run act as Taktus's own identity.** Taktus's own identity is for what
  Taktus does on its own behalf towards a service (ADR-0033). A schedule acts on behalf of
  whoever made the version active, as a command from any channel acts for its sender.

## Consequences
- `TAKTUS_PROVISIONAL_IDENTITY`, the provisional adapter and the field `provisional` of a
  resolution are gone. DEC-0013's obligation is met.
- The identity port gains `identity()` and `unknown_sender()`; `IdentitySource` is new. The
  connector port gains `ChannelReplies` and the reply operation's name.
- Migration 0015: the tables `identity`, `channel_link`, `link_code`, and
  `process.activated_by`.
- `taktusctl identity add | key | links | revoke`; `POST /identity/link-codes` on the surface.
- `taktusctl run` refuses an identity the tenant does not know. Scripts add theirs first.
- A webhook delivery whose sender is not linked is no longer kept as an intake event.

## Where this promise ends
- **Authorisation is not here.** Who may add identities, revoke links or act as whom is UC-7.3.
  Today whoever can run the command line against the database can do all of it, and can name
  any identity of the tenant.
- **The account key is a bearer secret.** Whoever holds it acts as the identity on the surface.
  It does not expire; a new key retires it. The surface is only as private as the network in
  front of it.
- **One account, one identity, across tenants, by reading each tenant in turn.** Two links for
  one account made in two tenants in the same instant are not prevented; within a tenant they
  are.
- **The reply reaches the channel only where the connector declares the reply operation.**
  Elsewhere the sender is not answered, and the outcome says so. A failed reply is not retried
  by Taktus.
- **A code found in a message links the sender who wrote it.** Whoever reads the code before
  it is used, and writes it first from another account, links that account to the identity.
  The 30 minutes and the single use bound that window; they do not close it.
- **The identity source is a port without an adapter.** Nothing of a particular directory or
  sign-in is connected yet.
- **The command line names, it does not authenticate.** A version registered as an identity
  that is later removed fires nothing; nothing removes identities yet.
