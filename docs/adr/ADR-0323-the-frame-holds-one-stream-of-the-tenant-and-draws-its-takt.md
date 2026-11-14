# ADR-0323 — The frame holds one stream of the tenant and draws its Takt

**Status:** accepted · amends ADR-0063 (when the web app reads a level again) and the web side of
ADR-0055 (the stream of changes) · DEC-0239 items 3 and 4; UC-6.10, UC-13.7

## Context

Each live page opened its own stream of changes and read its level only once the stream's first
event, the snapshot, arrived. For the tenant, the server built that snapshot from every run the
tenant ever had: 1 second and 1.2 MB at 3,000 runs, before the start page drew anything. The web
app then discarded the snapshot and read the level anyway.

The mark in the bar beat only on pages that followed a stream. On every other page the frame
showed nothing alive. The change events carried what changed, and the web app threw it away.

The owner asked that, from the start page on and throughout the app, one sees that a system lives
here and that it works: a pulse, a Takt (DEC-0239).

## Decision

### 1. One stream in the frame

The frame opens one stream of the tenant's changes when it opens: `GET /changes?snapshot=position`.
With `snapshot=position` the surface sends a snapshot that carries its position only, no runs. A
surface that does not know the parameter sends the full snapshot, and the frame ignores its runs.

The frame keeps, for the open visit:

- whether the stream is connected;
- how many changes arrived;
- the last 200 changes, each as the event carried it.

The mark in the bar beats once for each change, on every page, where motion is allowed.

### 2. Pages follow the frame's stream

A live page reads its level at once, without waiting for an event. It then listens to the frame's
stream and reads again, coalesced as before (ADR-0063), when:

- a snapshot arrives, because the stream reconnected and changes may have been missed;
- a change concerns it: its run for a run page and its stages; its process for a process page,
  by the change's `process` field. Where a change carries no `process`, a process page reads
  again on every change.

Today reads again on every change. No page opens a second stream.

### 3. The Takt strip

The pulse card on Today (ADR-0322 §4) draws the last 60 minutes as 60 marks, one per minute. A
mark's height follows how many changes were recorded in that minute. A failure in a minute is
drawn as its own mark in the alert family, by form and not by colour alone.

- The strip is drawn from recorded changes only: `GET /changes/recent?minutes=60` on opening,
  then the changes the frame's stream delivers.
- Only the newest arrival is animated, once, with the design system's `highlight` motion. Every
  earlier mark is still. Nothing from the past is replayed as motion.
- With no change in the 60 minutes the strip is flat and still: an idle tenant looks idle.
- Where motion is not allowed, nothing on it moves; the marks are the same.
- Its text equivalent says how many changes were recorded in the 60 minutes and when the last one
  was.

### 4. What the web app reads, in one place

Every read the surface offers for this (ADR-0317 to ADR-0319) is behind a typed adapter in
`web/src/lib`:

| Read | Adapter | What the web app takes |
|---|---|---|
| `GET /levels/today` | `todayData.ts` | `overview`, `counts`, `waits` and `marks` |
| `GET /changes/recent?minutes=60` | `takt.ts` | `changes` and `complete` |
| `GET /changes?snapshot=position` | `pulse.ts` | the position; the snapshot says `listed: false` |
| `GET /runs?state=&process=&cursor=&limit=` | `runs.ts` | `runs` and `next` |
| `GET /levels/processes/{id}` | `ProcessView.svelte` | `runs`, `counts` and `next` |

`GET /levels/today` is shared by the frame and Today for 15 seconds, so that opening Today reads
it once.

## Consequences

- Today draws as soon as its level is read, whatever the tenant's history.
- Every page shows the system's pulse, not only the live ones.
- A run page and a process page no longer open a stream of their own.

## Where this promise ends

- **The strip shows changes, not work.** A step that runs for an hour without a recorded change
  leaves the strip flat in that hour. Now running says that it runs.
- **The history is what the surface keeps.** The surface lists at most its newest 500 changes of
  the hour; where it cut older ones off, the strip says so. Where the read fails, the strip starts
  empty when the page opens and fills as changes arrive, and says that in words.
- **One stream per tab.** Two tabs open two streams. Nothing is shared between tabs.
- **A dropped connection is said, not hidden.** While the stream reconnects, the frame says
  *Reconnecting*, and the strip draws nothing it did not receive.
- **No change is counted twice and none is invented.** A reconnect resumes from the last position
  received (ADR-0055 §6). A gap the surface answers with a fresh snapshot is not drawn as changes.
