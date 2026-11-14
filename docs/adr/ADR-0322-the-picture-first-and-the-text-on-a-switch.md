# ADR-0322 — The picture first, and the text on a switch

**Status:** accepted · amends ADR-0178 §3 (the start page, item 6 in particular), ADR-0121 and
ADR-0122 (how their pages show their text), ADR-0064 and ADR-0067 (where the text equivalent
stands) · DEC-0239 item 4; UC-6.10, UC-13.7, UC-10.4

## Context

UC-6.10 §2 requires that every representation has a text equivalent carrying the same figures and
states. The web app met it by printing an *As text* section under every drawing. Ten pages that
draw nothing printed their own lists a second time under *As text*. On a process page, the runs of
the version appeared once as a list and once more in the text. The start page showed an item that
waits up to three times: as a governance line, as an open report and as an operation line. It
carried an exactness statement on every process card, and a counter that a screen reader spoke at
every change.

The owner asked for the visual presentation by default, the text form one switch away, and no
duplicated content (DEC-0239 item 4).

## Decision

### 1. One component for the text equivalent

`TextEquivalent.svelte` holds the text equivalent of a drawing. It has two modes:

- **Picture** (the default): the drawing is shown. The text stays in the accessibility tree,
  hidden from sight by `.sr-only`. A screen reader reads it as before. The drawing itself stays
  `aria-hidden`.
- **Text**: the drawing is hidden and the text is shown in its place.

UC-6.10 §2 asks that the text equivalent exists. It does not ask that it is visible by default.
Both modes therefore meet it unchanged.

### 2. The switch

- Every page that draws a picture carries a *Picture | Text* control, two buttons with
  `aria-pressed`. A choice there holds for that page while it is open.
- The account group (ADR-0321 §4) holds the default for every page. It is kept by the device in
  `localStorage`. Where the storage is refused, the default is *Picture* for the visit.
- Where the system asks for forced colours, the default is *Text*: a drawing whose meaning rests
  partly on hue reads worse there.

### 3. One copy of everything

- A page that draws nothing has no *As text* section. Its lists are already its text.
- A list that is already text — the runs of a version, the steps running now — appears once. It
  is not repeated in the text equivalent; each row carries its own text.
- The exactness statement stands on the process page and the run page, not on every card of
  Today.
- Live state is said in one place, the frame's, and only when the connection opens or is lost.
  A count of changes is not spoken.

### 4. Today

ADR-0178 §3 is replaced by this order:

1. **The pulse card.** Its first row counts what waits for the reader, so that waiting work is the
   first thing read (UC-13.7 §2). Then the overview's sentence, the live state, and the *Takt
   strip* of the last 60 minutes (ADR-0323).
2. **The glance strip.** One tile each for: running now, waiting on a person, failed in the last
   24 hours, open incidents, alerts in effect. A tile the surface did not count is left out, never
   shown as zero. Beside them the operation's own sentence (ADR-0121): that it runs as expected,
   or which of incidents, alerts, backup and signals need a look. The four operation lines of
   ADR-0121 leave Today; each kind keeps its tab under *Operation* and its mark there.
3. **Waits**: one list of at most five items — decision requests and open reports merged and
   deduplicated by their identifier, and a raise of a level or a finding in review that waits —
   oldest due first, with a link to all of them on `#/waits`. The governance lines that wait for
   nothing stay at the foot of the page.
4. **Now running**: the steps running now, each leading to its run.
5. **Just happened**: the last ten changes the stream delivered, newest first.
6. **What runs**: the processes, each drawn as its cells, with the text equivalent of the
   overview in a `TextEquivalent`.

A tenant without a process sees the way to its first process before the pulse card (UC-10.4).

### 5. Loading, empty and failed are three states

`Skeleton`, `EmptyState` and `ErrorState` are the three ways a page says where its read stands.
A read that failed — a 5xx answer, a lost network, a body that is not JSON — is shown as a failure
with a way to read again. It is never shown as empty, and never as *Reading…* forever.
`read()` never throws: a failed request is an answer with status 0.

## Consequences

- No page shows the same list twice in either mode.
- The tests that held every element's text in the rendered page still hold: the text is in the
  page, visible or not.
- A reader who prefers the text sets it once in the account group.

## Where this promise ends

- **The default is per device.** It is kept in the browser's storage, not in the account. A
  reader on a second device chooses again.
- **The per-page choice is not kept.** Leaving the page returns it to the default.
- **Forced colours set the default only.** A reader can still choose *Picture* there.
- **The text equivalent is the surface's.** The web app shows the sentences the surface hands
  over and writes none of its own about a step or a run.
- **Today's tiles are the surface's counts.** A count the surface withholds from the reader, as
  the alerts from a reader who does not read them, has no tile; it is never shown as zero.
- **Today lists the five most urgent waits.** `#/waits` shows the same five and leads to every
  one of a kind on its own page; no page lists every wait of every kind at once.
