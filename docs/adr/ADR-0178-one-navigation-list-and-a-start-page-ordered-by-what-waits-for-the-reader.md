# ADR-0178 — One navigation list, and a start page ordered by what waits for the reader

**Status:** accepted · extends ADR-0063 (the web app), ADR-0067 (the overview), ADR-0121 and
ADR-0122 (the start page's lines), ADR-0177 (the design system) · DEC-0227 item 3; UC-13.7

## Context

The web app grew one page per question: the overview, decision requests, needs, levels,
findings, what acts, dependencies, incidents, alerts, backup, signals, streams, the catalogue,
the gallery, trials, tenants and the reader's own page. The frame reached seven of them from a row
of links in the bar. The others were reached only from a line on the start page, or not at all
from the frame.

The start page stacked its sections in the order they were built: the operation, the overview,
what governs, the reports. The section that asks the reader to act — a decision waiting, a need
open, a report to answer — came last.

`docs/vision/personas.md` names who reads Taktus. A decider answers requests. An employee works
beside Taktus and takes over where needed. An operator commissions work. A process owner defines
processes and their levels. Management sees cost, quality and risk. An administrator runs the
platform. Principle 7 asks for transparency fitted to the role: nobody sees everything, and
nobody is refused what their role needs. The surface already decides what a reader may read. A
kind it refuses has no line (ADR-0122), and an operation kind a reader may not read says who
reads it (ADR-0121).

## Decision

### 1. One list of destinations

`web/src/lib/navigation.ts` is the one list of the web app's destinations. Each entry carries
its route, its label, its band and its icon. Every width draws this list and no other.

The bands follow what the reader is trying to do, not which component answers:

| Band | Destinations | Who comes here first |
|---|---|---|
| **Now** | Today, Decisions, Needs, Yours | everyone: what waits for the reader |
| **Start work** | Ask for, Gallery, Streams | the operator and the employee |
| **Steer** | Levels, Findings, Trials, What acts, Dependencies | the process owner and management |
| **Keep running** | Incidents, Alerts, Backup, Signals, Tenants | the administrator |

A band is an order, not a permission. Every reader sees every destination, and the page says
what the surface lets this reader read.

### 2. The frame

- **The bar** carries the mark, the depth the reader stands at (overview, process, run, origin),
  the choice of theme, *Stop motion* and *Sign out*.
- **The navigation** is a column pinned at the start edge from Hubtask's `expanded` width
  (905 px) up. Below it, the column is a drawer the bar's menu button opens.
- **A skip link** to `<main>` is the frame's first tab stop. `Escape` closes the drawer.
- **A destination that waits for the reader carries a mark.** The frame reads
  `GET /operation` and the start page's governance lines once when it opens. A destination whose
  line says that something waits — a decision request, an open need, a raise, a finding in
  review, an open incident, an alert in effect, a failing backup, a red signal — carries a
  filled mark and the words *needs a look* for a screen reader. A kind the surface refuses adds no
  mark. The frame counts nothing the surface did not count.

### 3. The start page: *Today*

The start page keeps every section it had (ADR-0067, ADR-0121, ADR-0122, DEC-0218), in this
order:

1. **The sentence of the overview**, set large, with the state of the live stream. Beside it,
   how many changes arrived since the page opened. Each arriving change moves a beat mark once,
   where motion is allowed. That number counts the stream's own events, nothing else.
2. **For you**: the governance lines that wait for the reader, and the open reports.
3. **What runs**: the overview's areas and processes, each process with its cells, its figures
   and its exactness statement.
4. **What keeps the operation running**: the operation's sentence and lines.
5. **What governs the work**: the governance lines that wait for nothing.
6. **As text**: the overview's text equivalent.

A tenant without a process sees the way to its first process in the first section, before
anything else (UC-10.4).

## Consequences

- Every page is reachable from the frame, at every width.
- What waits for the reader is the first thing the start page shows, whatever the reader's
  role.
- The bar no longer carries destinations. *Ask for*, *Streams*, *What acts*, *Gallery*, *Yours*,
  *Trials* and *Requests* moved into the navigation; *Requests* is now called *Decisions*.

## Where this promise ends

- **The marks are read once.** The navigation's marks are read when the frame opens and again
  when the reader returns to *Today*. They do not follow the stream, so a request raised while
  the reader is on another page shows its mark only after that.
- **No search and no command palette.** Hubtask's bar carries both; the web app has no surface
  to search yet.
- **No bottom bar on a phone.** Below 905 px the navigation is a drawer; Hubtask's bottom bar of
  primary destinations is not built.
- **The bands are not personalised.** A reader cannot reorder or hide a band. The surface's
  refusals decide what a page says, and the frame decides only the order.
- **Not a view of a person.** No mark, figure or order names a person or compares readers
  (principle 14). A mark says that something waits for the reader, never how fast anyone
  answered.
