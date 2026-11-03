# Stage 1 as the repository shows it — 2026-10-18 to 2026-11-01

Stage 1 of Taktus's own development ran from 2026-10-18 to 2026-11-01 (DEC-0212, #87): P-02
refines every opened issue on the instance, and P-03 implements the issues handed to it with
the label `to-taktus`. This record lists what the repository's host shows of those two weeks:
every comment Taktus's app wrote, every pull request it opened, and what became of each. It was
read on 2026-11-04 from the host's API, the issue comments and pull requests by the app
`taktus-baton`, between 2026-10-18 and 2026-11-01 inclusive.

**What it does not hold.** The money of each run is in the instance's ledgers, not on the host,
so the money per merged pull request (USD 3, DEC-0207, #511) is not measured here. Nor are the
daily watch's reports (DEC-0197), which are kept on the owner's machine.

## P-03 Implementation

Seven issues were handed. P-03 claimed them in 24 runs, from version 19 to version 23.

| Issue | Runs | Given back at | Pull request by Taktus | Outcome |
|---|---|---|---|---|
| #317 | 4 | `read-pipeline` 2, `implement`, `pull-request-body-form` | none | taken back by a session and merged as #570 |
| #325 | 5 | `pull-request-body-form`, `read-pipeline`, `implement`, `wait-for-pipeline` 2 | none | open; built in package E |
| #326 | 2 | `pull-request-body-form` | #541, +72 −7, merged 2026-10-20 | closed |
| #327 | 2 | `pull-request-body-form` | #540, +266 −2, merged 2026-10-20 | closed |
| #335 | 4 | `implement`, `read-pipeline` 2 | #635, +115 −0, merged 2026-10-28 | two more pull requests on the same branch from the owner's account, #644 and #654, before it closed |
| #336 | 2 | `implement` | #636, +217 −3, merged 2026-10-28 | closed |
| #394 | 5 | `pull-request-body-form` 2, `implement` 2 | #575, +257 −7, merged 2026-10-23 | open: its remainder, the wall time after, is recorded in `docs/status/0.4.0.md` |

- **Five of seven** handed issues ended in a pull request Taktus opened and a person merged.
  Four merged without more work on the branch (#540, #541, #575, #636). #635 was followed by two
  more on its branch.
- **Where the 19 give-backs stopped.** `pull-request-body-form` 6 times, each on a description
  whose headings differed from the template, all before version 22 compared them by command.
  `implement` 6 times: an execution unit that did not start (3), a worker that could not be
  asked about an earlier assignment (1), a package index answering 502 through the egress proxy
  (1), and a tool the frame does not allow (1). `read-pipeline` 5 times, on a pipeline that had
  failed. `wait-for-pipeline` twice: a pipeline still pending after 2 400 s, and one not found.
  Every give-back says its step and its cause in the issue.

## P-02 Refinement

P-02 wrote the missing sections of the ready standard into 13 issues: #533, #546, #557, #604,
#619, #637, #638, #639, #649, #650, #658, #661 and #662. P-01 Roadmap control commented on its
issue #129 16 times.

## Findings

- **The money per merged pull request is measured on the instance only.** The host shows how
  many runs a pull request took, not what they cost. Five merged pull requests of 24 runs is the
  denominator #511 needs; the ledgers of those 24 runs are the numerator.
- **A quarter of the give-backs were the platform, not the task.** Of 19, 5 stopped because a
  unit or a worker could not be reached or a download failed, before the change was judged. A
  measure of money per merged pull request counts what those runs spent against the tasks; #511
  is where that is weighed.
