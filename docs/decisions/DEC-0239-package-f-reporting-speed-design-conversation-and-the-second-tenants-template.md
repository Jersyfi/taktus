# DEC-0239 — Package F: short reports, speed, design, conversation and the second tenant's template

**Category:** NON-BLOCKING
**Mode entry:** M3.6 and M3.15 (how work lands and what a release holds), DEC-0222 (concept mode); UC-1.11 §3 (what a person's own agent may do)
**Raised in:** the session of 2026-11-14, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-14
**Written after the answer:** the owner stated it in conversation on 2026-11-14; left out of the acceptance rate (DEC-0042).

## 1. What this is about

After `v1.0.0-beta.1` (DEC-0237) the owner reviewed the instance and the second tenant's
requirements. They asked for six things:

1. reports that are short and to the point;
2. a web app that loads fast, found slow on every view;
3. a design review: a visual presentation by default, the text form on a switch, a system that is
   seen to be alive, and no duplicated content;
4. conversation: Taktus usable as a chat agent of its own, and buildable from a person's own agent;
5. the second tenant's template prepared completely against the business's catalogue and answers,
   with nothing in the repository that leads back to the business;
6. the integration server cleared, so that the owner can build the instance again from the start.

## 2. Why you are being asked

How work lands and what a release holds are the owner's (M3.6, M3.15). What a person's own agent
may do is fixed by UC-1.11 §3, a requirement, which only the owner changes (mode 3). Deleting an
installation's data is never done without asking (CLAUDE.md §9).

**Sources checked:** DEC-0222 (concept mode), DEC-0236 and DEC-0237 (the last round and its
release), UC-1.11 and ADR-0131 (the agent surface), `docs/vision/non-goals.md` (no agent runtime
as a core product), DEC-0225 (live tests only for services the project runs on). None answers
scope, the agent's acts or the deletion.

## 3. What you must decide

How the six areas land; whether a person's own agent may build in Taktus and whether Taktus gets a
conversation of its own; what may be deleted on the integration server; whether a wiki is set up
now.

## 4. What you need to know to decide

Four analyses of 2026-11-14 found: a watch introduced in release 1.0 delivered every escalation of
the instance's history at once after the rollout, each about 1,300 characters long; the start page
waits for a snapshot of every run the tenant ever had and reads the run table seven to eleven
times; 31 navigation entries and content shown twice; the agent surface may read and start but
not build, and the conversation port of a session has no model behind it.

## 5. Options

### Option A — one concept round, both kinds of conversation, the installation deleted (recommended)

### Option B — separate pull requests, the agent surface only, keep the data

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-14
**Answer:** in the owner's words. On the reports: "Man kann mit der Nachricht nicht viel Anfangen,
weil die Meldung viel zu lang ist [...] dass Informationen kurz, knapp so viel wie nötig, so
wenig wie möglich, auf den punkt gebracht, übersichtlich, zusamengefasst werden sollt." On the
design: "dass es Standardmäßig die schöne visualisierte und anschaulich gesatltete Oberfläche
gibt und dann noch die optionale Textform zum aufrufen [...] dass hier ein System lebt wie ein
Lebendes gehirn [...] wie ein Puls/Takt hat." On the template: "Geschäftskritische Informationen
über abläufe dürfen nicht in dem Repo landen. Wir bereiten die Vorlage vollständig vor [...]
Testen wird es der Kunde und wir versuchen es mit best efford auszuliefern." Generally: "du
darfst nichts faken und nicht haluzinieren." To the questions: "Konzeptmodus, ein PR";
conversation "Beides, Taktus führt"; the server "Löschen ohne Backup"; the wiki "Kein Wiki
jetzt".
**Reasoning given:** the owner's requirement that information is short, to the point and
summarised; a provider must find what it needs at a glance.
**What it changes:**

1. **Package F is built in concept mode** on one branch and lands in one pull request. The
   session may merge it when green, tag `v1.0.0-beta.2` and publish it (DEC-0236's delegation,
   carried over).
2. **Reports are short.** Every message Taktus writes to a person leads with one line, says
   what is needed in at most a few lines and links to the full record; a backlog of old
   escalations is never delivered as a flood.
3. **The web app is fast.** No page waits for a full read of history.
4. **Picture first, text on a switch.** The visual presentation is the default; the text form is
   one switch away and stays in the accessibility tree, so UC-6.10 §2 holds unchanged.
5. **A person's own agent may build.** UC-1.11 §3 no longer keeps changing a process away from
   the agent surface: it may plan, ask a change or a description of a process, rehearse and
   commission a proposal and roll back, through the same services, read-back and confirmation as
   the web app. Steering a run and the emergency stop stay where they are.
6. **Taktus gets a conversation of its own** over its model port, in the web app and the chat.
   A vendor's agent program never leads that conversation; it may serve as a worker inside a
   step (`docs/vision/non-goals.md`).
7. **The second tenant's template** covers the business's catalogue completely, as product where
   it is generic and as private configuration where it is the business's; nothing that leads back
   to the business enters the repository, and traces found are generalised.
8. **The integration server's Taktus installation is deleted without a backup**: the namespaces
   `taktus` and `taktus-exec` with their database, volumes, secrets and release. Nothing else on
   the server is touched. A guide to build it again follows.
9. **No wiki now.** NEED-0021 stays open.

**Recorded in:** this pull request
