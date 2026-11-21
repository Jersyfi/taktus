# ADR-0316 — A message to a person is its report's short form, and a backlog is never a flood

**Status:** accepted · amends ADR-0045, ADR-0252 · extends ADR-0242 · UC-6.11, UC-4.5, UC-6.2 · DEC-0239

## Context

On 2026-11-14 the instance was upgraded from 0.2.0-rc.37 to 1.0.0-beta.1. The escalation watch
of ADR-0252 §3 started for the first time. It delivers every `run.escalated` entry that has no
`escalation.delivered`. The instance held escalations back to October, and the watch sent more
than eighty of them to the owner within two minutes.

Each message was about 1,300 characters long. Its headings were German, from the owner's
phrasebook, and everything under them was English: the record's sentences, run identifiers,
process references and internal phrases such as "(this package lacks: needed)" and "what is
needed is not in the record".

DEC-0239 answered both: every message leads with one line, says what is needed in at most a few
lines and links to the full record; a backlog of old escalations is never delivered as a flood.

A **report** is the record of one event that needs a person (ADR-0045). The **situation
package** is the five-part content an escalation's report carries (ADR-0252 §1). A **message**
is the report's rendering in a chat channel.

## Decision

### 1. A watch delivers what is current, one by one, and summarises the rest once

A watch that delivers ledger entries — the escalation watch, and the contract watch of
ADR-0315 — sorts every entry it has not handled yet into one of three groups:

- **Current.** Its run is still waiting for a person. It is the newest entry of its run. It
  happened within the backlog horizon, one hour before the look. The watch looks once a minute,
  so an entry older than an hour was not seen when it happened: the watch was not running.
- **Settled.** Its run no longer waits, or a newer entry of the same run exists. It is recorded
  as not sent, with the outcome `settled`, and says nothing to anyone.
- **Backlog.** Its run still waits, and it is older than the horizon.

Current entries are delivered one by one, at most three per role and look. Every backlog entry,
and every current entry over that limit, goes into **one** summary report per role and look:
"N older escalations are open", with each run listed in the report's record and its view. Each
of these entries is recorded as not sent, with the outcome `summarised` and the summary's
identifier.

`escalation.not_sent` is a new ledger kind. An entry that has `escalation.delivered` or
`escalation.not_sent` is handled and never looked at again. A time to react is watched only
for an escalation that was delivered on its own.

The rule is pure: `reporting/domain/service/backlog.py` sorts, and the watches act on its
answer.

### 2. A message is the report's short form

The report stays the full record: its title, what is needed, the steps, what stands still, the
date and its links, and for an escalation the whole situation package (ADR-0252 §1). The
repository text and the web app's view of the report show all of it. The message is the short
form:

1. **One headline**, bold, prefixed by the kind's word: what happened and to which process, by
   the process's name.
2. **What is needed from the reader.** For a decision request, a need and a date, each needed
   item of the report, as a quote of one line (UC-6.11 §2). For a failure, one short line from
   the phrasebook that names the options.
3. **A quote of one line** where the event has a text worth seeing — an error, a question. It
   is the record's text, cut to one line.
4. **The date** by which it is needed.
5. **One link** to the report's page in the web app, which holds the full package. Without a
   configured address the report's identifier stands in its place.
6. **The answer line**, as before.

A list — the daily report of signals — carries only what deviates, one line each, with that
line's link, at most eight lines and then "N more" with the link to the whole.

What a message must not carry: a run identifier, a process reference such as `name@6` or a
heading with nothing under it. Where a part of the record is missing, the message leaves it
out. The report's view and its repository text say which part is missing, as ADR-0252 §1
requires.

### 3. Taktus's own words come from the phrasebook

A report may carry a **brief**: its headline, its options line and its list lines as entries of
the phrasebook, with values. A value is a name, a number or a date, never a sentence. The
phrasebook's new section `briefs` holds those sentences per language; each entry is checked for
its placeholders as every other sentence is.

A sentence that Taktus writes into a record is English, because the record is part of the
repository's language (CLAUDE.md §9). Such a sentence enters a message in another language only
as a quote of one line. A quote is the record's text, set apart as a quote. Every other line of
the message is in the phrasebook's language.

A report raised without a brief is shown with its title as the headline. A title Taktus wrote
is English, so in a phrasebook of another language that headline is set apart as a quote too.

### 4. A test holds the form

`tests/components/reporting/test_message_form.py` renders a message of every kind and every
brief from realistic records, in English and in German. It fails a message that is longer than
400 characters without its addresses, a list longer than 400 characters plus 120 characters per
line, a line of Taktus's own outside the phrasebook's language, a run identifier or a process
reference outside an address, or a heading with nothing under it.

### 5. The scheduled report of a role

The report of a role (ADR-0242) is said in the language of the tenant's phrasebook. It lists
only what bears a decision or a consequence for its reader, one line each, with that line's
link to the web app where an address is configured. A period with nothing in it is one
sentence.

## Alternatives

- **Deliver the backlog, slowly.** Eighty messages spread over an hour are still eighty
  messages, and most were settled long ago.
- **Mark the backlog delivered without saying anything.** Runs that still wait would then be
  forgotten silently. One summary keeps them visible.
- **Translate the record into the owner's language.** The record is English by rule. A second
  record per language would be a second truth that can disagree with the first.
- **Drop the needed items from the message.** UC-6.11 §2 requires that the message carries the
  same needed items as the repository text and the view.

## Consequences

- A tenant hears of a current escalation within a minute, as before, and of a backlog once.
- The repository text and the view are unchanged; only the message is shorter.
- Every raiser that writes a report should give it a brief. One that does not still sends a
  short message, with its English title as a quote.
- A tenant that configured a phrasebook of its own before `briefs` existed keeps working. Its
  messages take the headline from the title until it adds the section.

## Where this promise ends

- **One hour is a configuration, not a measurement.** The horizon assumes the watch looks every
  minute. A watch that stopped for less than an hour delivers what it missed one by one, at most
  three per role and look.
- **Only the watches named here.** The escalation watch and the contract watch sort their
  backlog. A report raised directly by a run or a command is delivered when it is raised, and is
  not sorted.
- **The limit counts messages per look, not per day.** A tenant whose processes escalate three
  times a minute for an hour hears of up to three per minute, and of the rest in summaries.
- **A quote stays in the record's language.** Needed items, errors and the questions of decision
  requests are shown as written. In a German message they may be English. Translation is not
  built.
- **Not the conversations.** Replies to a person's question in the channel — a reading, a
  take-over, a change, the catalogue — keep their sentences. They are answers, not reports, and
  are already short.
- **Lengths are characters, not reading time.** 400 characters is what the test holds. It does
  not prove that a person grasps the message at a glance; the owner's review does.
