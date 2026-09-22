# NEED-NNNN — <title: what is needed, in five words>

**Kind:** <credential | account | access | purchase | action | information>
**Raised in:** <link to the pull request>
**Issue:** <link to the GitHub issue labelled needs-owner>
**Needed by:** <YYYY-MM-DD>
**Foreseeable since:** <the pull request in which the need became foreseeable; the same as Raised in when it was raised in time>

<!--
Copy this file to docs/decisions/open/NEED-NNNN-<slug>.md, with the next free needs number.
Fill every section. Replace every <placeholder>; the gate fails on any that remains.
A need is something only the owner can provide: a credential, an account, access to a system,
a purchase, an action on a server, information about an environment. It is not a decision —
there are no options — and it is not a note. Raise it when it becomes FORESEEABLE, not when
it blocks (ADR-0028 §1). Raising it is mode 2, entry M2.5 of anchors.taktus.md: the session
decides, nobody approves; providing it is the owner's.
The comprehension test: could the owner provide this, following section 4 alone, without
reading the diff, the session or any ADR? If not, the request is not finished.
Section 5 is not boilerplate: the repository is public, and a session never receives a secret
value. Say where the value goes instead.
-->

## 1. What is needed

<In plain words, for a reader who has read nothing else. One paragraph.>

## 2. Why

<What it unlocks, and which milestone or task depends on it. Name the process, the step, the
command that cannot run without it.>

## 3. By when

<The date from the header, and what happens if it is not there by then: what stays unproven,
what waits, what is built on an assumption instead.>

## 4. How to provide it

<The steps, in order, each one an act the owner can perform. Where it goes: the file, the
configuration key, the variable that points at the file (CREDENTIALS.md). Which permissions
and which scope, and no more. How long it should be valid, and when it rotates. The literal
commands where there are any, in code blocks, with no value in them. Where two ways exist,
both, and which is recommended and why.>

## 5. What it must never be

<Never pasted into a chat, never committed, never sent to a session, never put into an
environment variable a process listing shows, never named in this repository by the
deployment's own name for it. Where it goes instead, concretely.>

## 6. What happens next

<Once it is in place: what to tell the session — the literal sentence — or what runs on its
own without anyone saying anything.>

## 7. How to confirm

<A check the owner can run that says "provided correctly" without printing the value: a
command whose output is a status, a count, or a name, never the value.>
