# DEC-0127 — How a person's accounts are linked

**Category:** NON-BLOCKING
**Raised in:** [#173](https://github.com/Jersyfi/taktus/pull/173), from the owner's direction of 2026-10-10 recorded in NEED-0017 and NEED-0020
**Issue:** [#171](https://github.com/Jersyfi/taktus/issues/171)
**Needed by:** 2026-10-31
**Provisional answer:** The requirement stands as it is (Option B in substance): no new kind of link is built before the answer, and NEED-0017 and NEED-0020 keep their link codes. One part of Option A is taken now, because it cannot wait: the chat app's manifest in NEED-0018 asks for `users:read` and `users:read.email`, marked provisional there, so that the app you install on 2026-10-11 need not be installed again if Option A or C is chosen. Under Option B the two lines are removed and the app reinstalled; its token does not change.

## 1. What this is about

Taktus acts only for a person it knows. A message in a team chat, or a comment on the code
repository, comes from an **account** on that platform. Taktus acts on it only when that account
is **linked** to one **identity** — the person's account in Taktus, with their rights and their
place in the organisation. A message from an account linked to nobody does nothing; its sender
is offered how to link it.

Today a link is made in exactly two ways. Either the person creates a short-lived code in Taktus
and writes it from the platform account, which proves both sides at once. Or the organisation's
own directory of people — its **identity source**, such as the sign-in system its staff use —
answers which identity an account belongs to. A link is never inferred because a name or an
address matches.

On 2026-10-10 you gave a direction: linking should cost users and administrators little effort.
Taktus can read a platform's member list; an administrator should only have to say which member
is which person, so that Taktus knows each person's accounts across platforms. Several
combinations should work — linked automatically, linked by hand, or only the person's handle
noted — and how it works must be proven technically, against the platforms Taktus itself uses:
the team chat and the code repository.

What was attempted, and what was found:

- **The chat service's member list** can be read by Taktus's own chat app with the permission
  `users:read`. With a second permission, `users:read.email`, each member's e-mail address comes
  with it, together with a flag saying whether the service confirmed that address. Each member
  also carries a flag for automations and one for deactivated accounts. The list is read in
  pages of up to 200; the service allows about twenty reads a minute. Taktus's chat app does not
  ask for either permission yet: it is set up on 2026-10-11 (NEED-0018).
- **The repository service's member list** for a repository is the list of its collaborators.
  Taktus's repository app may already read it: the endpoint needs only the permission
  "metadata: read", which the app holds (NEED-0013). Read once on this repository on 2026-10-10,
  it returned each account's number, login name, kind and role — and no address. An
  organisation's member list would need a further permission, "members: read"; this repository
  belongs to a person, not an organisation, so it has none.
- So on the chat service a link can be **suggested** from a confirmed address; on the
  repository service it cannot, and an administrator picks the account by its login name.

## 2. Why you are being asked

The entry M3.15 of this project's anchor page gives you **"What a use case requires"** — its
outcome, its verification condition and its boundary, sections 1 to 3 of the use case. The requirement
"every command belongs to one identity" (UC-1.7) says in its section 2 that a link is made only
by the person confirming it or by the organisation's identity source. A link made by an
administrator from a member list is neither, so the direction cannot be followed without
changing what that requirement says.

**Sources checked:** `docs/vision/` — principle 14 forbids watching or appraising a person, which
bounds what a member list may be used for, and principle 11 asks for data protection, which
bounds what of it may be kept; neither says who may make a link. ADR-0040 decided the two ways
of today and rejected linking by a matching name or address, because an address can be set by
anybody; it says nothing of an administrator choosing from a list. `anchors.md` and
`anchors.taktus.md`: M3.15 gives the requirement to you; no mode-1 or mode-2 entry covers it,
and it is not a restoration (M2.7), because the vision does not contain it. The register: no
earlier decision touches how a link is made; DEC-0013 only retired the stand-in identity.

## 3. What you must decide

Which ways of linking a platform account to a person does Taktus accept, and what may an account
linked each way do?

## 4. What you need to know to decide

**Four kinds of link.** Option A records every link with the way it was made:

| Kind | How it is made | Who must act |
|---|---|---|
| `self` | the person proves in Taktus that they hold the account: the code of today, or later a sign-in to the platform from their Taktus account | the person, once per platform |
| `source` | the organisation's identity source answers it — including, on a platform the tenant declares as governed by that source, an account whose confirmed address equals the identity's | nobody, once the platform is declared |
| `admin` | an administrator picks the account from the member list Taktus read, alone or by confirming Taktus's suggestions several at a time | an administrator, a few clicks per person |
| `handle` | Taktus only knows where to reach or mention the person on the platform | an administrator, or Taktus from the member list |

A **suggestion** is a pairing Taktus proposes because a member's confirmed address equals an
identity's address. It links nothing until an administrator confirms it. A **confirmed address**
is one the platform itself checked, by a message the address's owner had to answer.

**Who can pretend to be whom, under each kind.** This is the security consequence of every
option.

- `self`: only someone who reads a person's unused code within its 30 minutes and writes it first
  from another account. That holds today.
- `source`: whoever controls the organisation's identity source. On a platform declared as
  governed by it, also whoever can give an account a confirmed address there — the platform's
  own administrators. The tenant takes that trust on when it declares the platform.
- `admin`: a Taktus administrator can make any account act as any person. That is not new: the
  administrator can already act as any identity from the command line (ADR-0040). New is the
  **mistake** — two members called "Jan", and the wrong one picked. The wrong holder then acts
  with the other person's rights until the link is revoked.
- `handle`: nobody can act through it. A message from that account is treated as from an unknown
  sender. The only risk is the reverse: a message meant for the person reaches a wrong handle. A
  handle is therefore used to mention a person, never as the address a report is sent to.

**Acts that need a stronger link.** Option A lets a tenant name acts that only a `self` or
`source` link may perform. By default that is answering a decision request at an anchor — a point
where a person must decide (CLAUDE.md §8). An administrator's mistake can then never decide in
someone else's name. A tenant may lower it to `admin` for its own anchors.

**What reading a member list means for people.** The list names everyone on the platform, not
only Taktus's users. Under Option A and C Taktus reads it only when an administrator asks, keeps
of each member only the account's identifier, its display name and its confirmed address, keeps
nothing of a member who is neither linked nor suggested, and drops a suggestion nobody confirmed
within 30 days. It never reads presence, activity or anything else a member list may carry, and
never uses the list for anything but linking (principle 14).

**What it commits the project to.** Every link record gains its kind, and the ledger names the
administrator who made an `admin` link. Removing a kind later means revoking every link of that
kind. A later sign-in to the platform as a `self` method needs, for each platform, a client
secret of Taktus's app: a need of its own, raised when that is built.

**What an architecture record would decide.** Before anything of Option A or C is built, a
design record amending ADR-0040 settles: the kind on the link record, its migration, and the
ledger outcome per kind; a read-only member-list operation on each connector, named by
capability, never retried; that suggestions are computed by the identity component, never by a
connector; that the strength of a link travels with the resolution of a sender, and where the
decision request checks it; the message Taktus sends to an account an administrator linked; the
data kept from a member list and for how long; and the platform sign-in as a later `self` method.

## 5. Options

### Option A — Four kinds of link, each recorded with how it was made (recommended)

- **Meaning:** UC-1.7 §2's fourth bullet, "A link is made only by the person confirming it in
  their Taktus account, or by the organisation's identity source. It is never inferred from a
  matching name or address.", is replaced by:

  > - Every link records how it was made: by the person proving in their Taktus account that
  >   they hold the channel account (`self`); by the organisation's identity source (`source`);
  >   by an administrator choosing the account from the channel's member list that Taktus read
  >   (`admin`), naming that administrator; or as the person's handle only (`handle`).
  > - A link is never made from a matching name or address alone. Where the channel states a
  >   confirmed address equal to an identity's, Taktus suggests the link; a suggestion becomes a
  >   link only when an administrator confirms it, one or several at a time, or, on a channel the
  >   tenant declared as governed by its identity source, as a `source` link.
  > - An event from an account linked only as a handle is treated as from an unknown sender.
  > - When an administrator links an account, Taktus tells the account in the channel which
  >   identity it was linked to and by whom, and its holder can revoke the link there.
  > - An act the tenant reserves to strong links — by default answering a decision request at an
  >   anchor — is accepted only from a `self` or `source` link.
  > - Taktus reads a channel's member list only when an administrator asks, keeps of a member
  >   only the account's identifier, display name and confirmed address, keeps nothing of a
  >   member neither linked nor suggested, and uses the list for nothing but linking.

  Section 1 gains "or by an administrator who links it" after "through the organisation's own
  identity source".
- **Consequence:** linking a team becomes: read the chat's member list, confirm the suggested
  pairs, pick the rest by name. On the repository, pick by login name. Each person may still link
  themselves with the code. For you now: NEED-0017 and NEED-0020 can be provided by an
  administrator's link, but your answers to decision requests in the chat then need a `self`
  link — the code you would write anyway, once.
- **Effort:** a design record and about four to six days of session work: the kind and the
  migration, the member-list operation on both connectors, suggestions, the administrator's
  commands, the message to a linked account, the check on decision requests. Nothing for you
  beyond the two chat permissions already asked for.
- **Reversibility:** cheap before it is used. Afterwards a kind is withdrawn by revoking its
  links; nobody loses an account.
- **Why recommended:** it follows the direction — every combination you named works — and keeps
  what the requirement protects: nobody is linked by a match alone, and the acts that bind are
  kept to links the person proved. The one new risk, an administrator's mistake, is told to the
  account that was linked and cannot answer at an anchor.

### Option B — The requirement as it is

- **Meaning:** a link stays the person's code or the organisation's identity source. Nothing is
  built. The two chat permissions are removed from the manifest.
- **Consequence:** each person writes a code once per platform. For a small team that is a few
  minutes each; for a department it is a rollout that waits for its slowest member. Taktus never
  holds a member list.
- **Effort:** none; one reinstall of the chat app after the permissions are removed, which keeps
  its token.
- **Reversibility:** cheap; Option A can be chosen later.

### Option C — Administrators pick, the account's holder confirms

- **Meaning:** as Option A, except that an `admin` link, and a confirmed suggestion, take effect
  only when the account's holder answers "yes, that is me" to Taktus's question in the channel.
  Until then the account is from an unknown sender.
- **Consequence:** an administrator's mistake can no longer act at all: the wrong holder would
  have to claim someone else's name. Every person must still act once, as under Option B,
  though with one click instead of a code. The administrator's word still decides who the
  person is, so an `admin` link stays weaker than `self` for the acts reserved to strong links.
- **Effort:** Option A's, plus about a day for the question and its answer.
- **Reversibility:** cheap; it can be relaxed to Option A by configuration later.

## 6. What is blocked

Nothing is blocked. The provisional answer keeps the requirement as it is, so the link codes of
NEED-0017 and NEED-0020 work as described. Building Option A or C waits for this answer: a
requirement is never changed in the pull request that implements it.

Needed by **2026-10-31**, the date of NEED-0017. If no answer has arrived by then, the
provisional answer stands: the code stays the only way a person links an account, and the chat
app holds two permissions nothing uses yet. Removing them later costs one reinstall.

## 7. How to answer

- "DEC-0127: Option A."
- "DEC-0127: Option B."
- "DEC-0127: Option C."

A free-text answer — for instance Option A with the strong-link default changed — is read back
as an interpretation and confirmed before it is acted on.
