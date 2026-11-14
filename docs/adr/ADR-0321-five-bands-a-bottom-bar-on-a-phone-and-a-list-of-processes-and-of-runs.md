# ADR-0321 — Five bands, a bottom bar on a phone, and a list of processes and of runs

**Status:** accepted · amends ADR-0178 §1, §2 and its section *Where this promise ends* · DEC-0239 item 3; UC-13.7

## Context

ADR-0178 gave the web app one list of destinations. By release 1.0 that list held 31 entries in
four bands, where ADR-0178 named 17. Several entries shared one icon. A run or a process was
reachable only from Today or from a link on another page: there was no list of processes and no
list of runs, although `GET /runs` exists. The depth in the bar (overview, process, run, origin)
showed where the reader stood but led nowhere. *Today* was marked current on every process, run
and origin page. On a phone, every destination sat in a drawer, and the bar was crowded between
421 and 480 pixels.

The owner reviewed release `v1.0.0-beta.1` and found the app hard to find one's way in and
cluttered (DEC-0239 item 3).

## Decision

### 1. Five bands, each with its first entries and a fold

`web/src/lib/navigation.ts` stays the one list. It is ordered in five bands by what the reader is
trying to do:

| Band | First entries | Under *More* |
|---|---|---|
| **For you** | Today, Ask Taktus, Decisions, Needs, Yours | Coach, Proposed |
| **Work** | Processes, Runs, Start work | Streams, Chains, Discoveries |
| **Steer** | Levels, Findings, Value and figures, Trials | Introduction, Structure, Data protection |
| **Depends on** | What acts, Dependencies | |
| **Keep running** | Operation | Administration, Tenants |

A fold is a `<details>` element per band. It opens by itself when the reader stands on one of its
entries.

Pages that answer one question from several sides share one destination and carry tabs:

- **Start work**: *Ask for*, *Gallery* and *Plan*.
- **Value and figures**: *Value*, *Figures* and *Reports*.
- **Operation**: *Incidents*, *Alerts*, *Backup*, *Signals* and *Health*.

*Ask Taktus* leads to `#/ask`. The conversation area builds that page; the frame only names it.

### 2. A list of processes and a list of runs

- **Processes** (`#/processes`) lists every process the overview hands over, with its level,
  how many of its runs work and wait, and a link to its graph.
- **Runs** (`#/runs`) lists the runs the reader may see, newest first, a page at a time, with
  their process, state, whether each is a rehearsal and when each was created. It can be narrowed
  to a state and to a process. It reads `GET /runs`.

A process page shows its newest ten runs and leads to *Runs* narrowed to that process for the
rest.

### 3. A trail of links instead of the depth

The bar's depth becomes a trail of links: *Processes › the process › the run › the origin*. Every
step of the trail but the last is a link. A process, a run and an origin are current on
*Processes* or *Runs*, no longer on *Today*.

### 4. The frame by width

| Width | Navigation | Account |
|---|---|---|
| from 905 px | the column pinned beside the content | a menu behind the account button in the bar |
| 600 to 904 px | a drawer behind the bar's menu button | the same menu |
| below 600 px | a bottom bar: *Today*, *Waits*, *Runs*, *Menu* | in the sheet *Menu* opens |

*Waits* (`#/waits`) is every item that waits for the reader in one list; Today shows the first
five of it. *Menu* opens a sheet with the whole list and the account group. The account group
holds the theme, *Reduce motion*, the default of *Picture* or *Text* (ADR-0322) and *Sign out*.
Below 600 px the frame sets the design system's `spacious` density.

### 5. Marks that follow the stream

The marks of what waits are read when the frame opens. The frame holds one stream of the tenant's
changes (ADR-0323). A change of a decision request reads the marks again, so a request raised
while the reader is on another page shows its mark without a return to *Today*. The reads are
shared with the page that shows the same lines, so they are not made twice.

## Consequences

- Every page stays reachable from the frame at every width, and every page is current on exactly
  one destination (`navigation.test.ts`, `test_web_design_system.py`).
- The first entries of all bands are 15, where 31 stood in one column before. The rest sit one
  click further, under *More*, or on a tab.
- *Today* is current on Today and on *Waits* only.

## Where this promise ends

- **The marks follow decision requests, not every kind.** A change on the stream that is not a
  decision request does not read the marks again. A new incident, alert or finding shows its mark
  the next time the frame reads the lines.
- **The lists read what the surface pages.** *Runs* is as complete as `GET /runs` lets the reader
  see. Narrowing by state or process is done by the surface where it supports it, otherwise on
  the page that was read.
- **No search and no command palette.** Finding a run or a process by its name is still not
  built.
- **The bands are not personalised.** A reader cannot reorder them or move an entry out of a fold.
- **Not a view of a person.** No mark, list or order names a person or compares readers
  (principle 14).
