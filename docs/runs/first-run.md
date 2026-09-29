# The first run

**2026-09-23.** The first time an issue of this repository became a pull request opened by
Taktus, with every check of that pull request green. It is the completion criterion of
milestone `0.1.0`, and this is the record of what it took.

**In one sentence:** P-02 Refinement read issue [#11](https://github.com/Jersyfi/taktus/issues/11),
asked a model for its acceptance criteria and wrote them as a comment, in six seconds and on
the first attempt; P-03 Implementation needed **eight attempts** and about **$6.10**, of which
seven failed on four defects in Taktus and one flaky test, and none on the change itself — the
coding worker's change was right the first time and every time after.

The pull request is [#38](https://github.com/Jersyfi/taktus/pull/38). Nobody has merged it;
that is the owner's.

---

## 1. What ran

| | |
|---|---|
| **P-02 Refinement** | `run_b55bf2cba3d3dd282bb9`, 12:11:13–12:11:19 UTC, **finished**. Six steps, one attempt |
| **P-03 Implementation** | eight runs, 12:11:20–14:00:39 UTC. The last, `run_e2db6d05d5990587e022`, **finished**: fourteen steps, a branch, a green pipeline, a pull request, a label |
| **Ledger** | 369 entries in the chain across every run of the day, **verifies**. 48 entries for the last run, and 14 provenance records, one per completed step, **chain verifies** |
| **State** | in memory with a file snapshot, not a database — development only, and the first thing a deployment changes |
| **Identity** | `idn_owner`, provisional (DEC-0013), on every line |
| **Execution** | the coding worker by endpoint, started as a process on the session's machine. **Nothing isolated it** — see §5 and DEC-0022 |

**P-02's outward effect** was the first a Taktus process has ever produced: a comment on issue
#11 with seven acceptance criteria under the heading `## Acceptance criteria`. It was written
once and never rewritten; all eight P-03 attempts read that same comment, and a second P-02
pass refused itself on its own check, correctly.

## 2. Consumption, estimate against actual

This is what the report is for. ADR-0005's budget mechanism and ADR-0010's Takt are calibrated
from numbers, and until today there were none.

### P-02 Refinement — `run_b55bf2cba3d3dd282bb9`

| Step | Method | Exactness | Estimated | Actual | Time |
|---|---|---|---|---|---|
| `read-issue` | rule | sourced | nothing | quota 1 | 1 s |
| `read-comments` | rule | sourced | nothing | quota 1 | under 1 s |
| `admit` | rule | exact | nothing | — | under 1 s |
| `refine` | **llm** | sourced | **nothing** | **456 in / 218 out tokens** | **4 s** |
| `compose-comment` | rule | sourced | nothing | — | under 1 s |
| `write-criteria` | rule | sourced | nothing | quota 2 | 1 s |
| **the run** | | | quota limit 60 | **456/218 tokens, quota 4** | **6 s** |

**Nothing in P-02 was estimated.** Only a `worker` step is: the engine asks the worker, and a
`rule`, a `wait` and an `llm` step demand nothing at admission. So the model step that is the
whole point of P-02 passed admission with an estimate of zero and then spent 674 tokens.
Nobody noticed, because the quota limit counts connector requests and the run used 4 of 60.

**That is the first finding for ADR-0005**, and it is structural rather than a bug: admission
control holds a run against an estimate it does not have, for the one kind of step whose demand
varies most. The budget of `0.2.0` reserves the estimate at admission — and it needs an
estimate for an `llm` step to reserve one. The input is countable before the call, because the
prompt is rendered; the output is bounded by `max_output_tokens`. The estimate is available and
simply not asked for.

The money for `refine` is **not reported at all**: the model adapter records tokens and no
price. On the smaller model the step cost well under a cent, which is exactly why it is easy
to leave unmeasured and wrong to.

### P-03 Implementation — the run that finished, `run_e2db6d05d5990587e022`

| Step | Method | Exactness | Estimated | Actual | Time |
|---|---|---|---|---|---|
| `read-issue` | rule | sourced | nothing | quota 1 | 1 s |
| `read-comments` | rule | sourced | nothing | quota 1 | under 1 s |
| `context` | rule | sourced | nothing | — | under 1 s |
| `admit` | rule | exact | nothing | — | under 1 s |
| `implement` | **worker** | tolerant | **60 000 in / 6 000 out tokens, $1.00, 12 steps, 600 s, confidence low** | **206 393 in / 170 out tokens, $0.766** | **161 s** |
| `branch-name` | rule | exact | nothing | — | under 1 s |
| `create-branch` | rule | sourced | nothing | quota 11 | 7 s |
| `wait-for-pipeline` | wait | — | nothing | quota 22 | **311 s** |
| `read-pipeline` | rule | sourced | nothing | quota 2 | 1 s |
| `verify` | rule | exact | nothing | — | under 1 s |
| `pull-request-title` | rule | exact | nothing | — | under 1 s |
| `pull-request-body` | rule | sourced | nothing | — | under 1 s |
| `open-pr` | rule | sourced | nothing | quota 2 | 2 s |
| `label` | rule | sourced | nothing | quota 2 | 2 s |
| **the run** | | | currency limit $5.00, quota limit 200 | **206 393/170 tokens, $0.766, quota 41** | **486 s** |

### The one estimated step, eight times over

The same issue, the same acceptance criteria, the same brief, eight times:

| # | Outcome | Tokens in | Tokens out | Money | Time |
|---|---|---|---|---|---|
| 1 | pipeline red — the file mode | 116 902 | 106 | $0.449 | 94 s |
| 2 | pipeline red — the status gate | 161 491 | 122 | $0.567 | 120 s |
| 3 | pipeline red — a flaky test | 110 531 | 84 | $0.833 | 166 s |
| 4 | pull request opened, its own checks red | 247 401 | 192 | $1.078 | 255 s |
| 5 | pull request opened, its own checks red | 148 015 | 128 | $0.789 | 160 s |
| 6 | pull request opened, its own checks red | 257 289 | 195 | $0.736 | 166 s |
| 7 | pull request opened, its own checks red | 219 773 | 157 | $0.875 | 147 s |
| 8 | **pull request opened, every check green** | 206 393 | 170 | $0.766 | 161 s |
| | **the estimate, every time** | **60 000** | **6 000** | **$1.00** | **600 s** |

**What the estimate gets right and wrong:**

- **Input tokens: under by 1.8× to 4.3×.** Estimated 60 000, measured 110 531 to 257 289. The
  estimate is a configured constant (`--estimate-tokens-in`, default 60 000), and the worker
  says as much: `confidence: low`.
- **Output tokens: over by 30× to 70×.** Estimated 6 000, measured 84 to 195. What the worker
  reports as output is the agent's closing text, not what it wrote into files along the way.
  The estimate is for one quantity and the measurement is of another.
- **Money: the closest of the three, and it was exceeded once.** Estimated $1.00, measured
  $0.449 to $1.078. Attempt 4 spent **7.8 % more than was reserved for it**. With a per-step
  currency limit of $1.00 instead of a run limit of $5.00, that step would have passed
  admission and then broken its reservation — the degradation DEC-0012 records: a currency
  limit holds against an estimate, and money is known only when the assignment ends.
- **Money is not a function of the tokens reported.** Attempt 3 spent $0.833 for 110 531 input
  tokens; attempt 1 spent $0.449 for 116 902 — more tokens, half the money. Caching and the
  model mix inside the agent decide the bill, and neither is visible in what Taktus records.
  **A currency budget converted into tokens (ADR-0005) cannot be converted back from these
  figures.**
- **Wall clock: over by 2.4× to 6.4×.** Estimated 600 s, measured 94 to 255 s.
- **Steps: about right.** Estimated 12; the agent produced 10 to 14 change artifacts.

**What the worker's defaults should be, from this data.** A reservation must not under-reserve,
so these are the maxima seen and not the means:

| Flag | Today | From this run |
|---|---|---|
| `--estimate-tokens-in` | 60 000 | **260 000** |
| `--estimate-tokens-out` | 6 000 | **200** |
| `--estimate-currency` | 1.00 | **1.10** |
| `--estimate-wall-seconds` | 600 | **300** |
| `--estimate-steps` | 12 | **14** |

**The variance is the number that matters most.** For one small, well-specified issue in one
repository, across eight runs of the same brief: input tokens vary by **2.3×**, money by
**2.4×**, duration by **2.7×**. Anyone planning a takt from a single measurement of a coding
step will be wrong by a factor of two as a matter of course. An estimate should carry a spread
rather than a point, and `confidence` is the field that already exists to say so.

### What the whole day cost

| | |
|---|---|
| The coding step, eight attempts | **$6.09** |
| P-02's model step | 456 + 218 tokens; under a cent, and not reported as money |
| Connector requests | 4 for P-02, 297 for the eight P-03 runs |
| Wall clock, first command to green pull request | 1 h 50 min |
| of which waiting for the pipeline | **about 38 min** — eight waits of roughly 5 min 20 s |
| of which the coding worker working | **about 21 min** |

**The pipeline is the bottleneck, not the model.** `wait-for-pipeline` took 311 s of the last
run's 486 s — 64 % of the wall clock — and 22 of its 41 quota units, polling every 30 seconds.
The expensive step took a third of the time. An event instead of a poll
(`pipeline_run.completed` already reaches the intake) would make the wait free in quota without
shortening it by a second.

## 3. Every point where a person had to step in

Nine, of which one was foreseen and seven were not.

1. **Providing the three credentials** — the owner, before any of this. Foreseen: NEED-0001,
   NEED-0002 and NEED-0003, provided 2026-09-22 and confirmed 2026-09-23 in #23.
2. **Running P-03 alone.** `tools/first_run.sh 11` runs P-02 and then P-03. After the first
   pass P-02's check refuses the issue — the criteria are there — and the script stops with it,
   before P-03. Every attempt after the first was started by hand, from a script in a scratch
   directory outside the repository. → issue [#30](https://github.com/Jersyfi/taktus/issues/30).
3. **Deleting the branch `taktus/issue-11`, seven times.** A new run derives a new idempotency
   key, finds a branch carrying somebody else's, and ends `conflict` — correct for the
   contract, and it means a person clears up between attempts. Same issue.
4. **Diagnosing the file mode** and correcting the connector → DEC-0020.
5. **Deciding, provisionally, whether a pull request Taktus opens must carry a status update**
   → DEC-0021, open, issue [#27](https://github.com/Jersyfi/taktus/issues/27).
6. **Re-running a flaky CI job** → issue [#29](https://github.com/Jersyfi/taktus/issues/29).
7. **Trying to resume after that**, and finding that a resume cannot pick up a pipeline that
   has turned green → issue [#31](https://github.com/Jersyfi/taktus/issues/31).
8. **Correcting the pull request description**, over four attempts → DEC-0025 and issue
   [#34](https://github.com/Jersyfi/taktus/issues/34).
9. **Reviewing and merging #38** — the owner, still to come, and the one intervention the
   design intends.

Two to eight are the honest cost of a first run. Only the first and the last are supposed to
be there.

## 4. The four defects, in the order they were met

Each stopped the run at a step boundary with a reason. **Not one was a defect in the change the
coding worker made**, which was right on the first attempt and on every attempt after.

### DEC-0020 — the branch lost the file mode

The connector wrote every tree entry as `100644`, so `tools/preflight.sh` arrived on the branch
without its executable bit. Every job of the pipeline died on its first line —
`make: tools/preflight.sh: Permission denied` — before running a single check. P-03 read that
verdict, refused the change, correctly, and opened nothing. The verdict was right about the
pipeline and wrong about the change.

Corrected, with a test that fails without the fix. A file that is *new* and should be
executable would still arrive plain: issue
[#28](https://github.com/Jersyfi/taktus/issues/28).

### DEC-0021 — the status gate, which the worker knew nothing about

A change under `tools/` must come with a change to `docs/status.md`, and nothing told the
worker so. The gate is right; the process was incomplete. The provisional answer — the
repository's rules hold, and the run asks the worker to meet them — is in force, and the
question itself is open for the owner.

**What the worker then wrote is the evidence that decision needs.** Given the rule, it updated
the date, corrected the "accounts for" line, noticed that #22 had merged and renumbered the
section below. Plausible, useful, and partly a guess: it cannot know that it is itself the
first live run. A reviewer has to read it. That is Option A working exactly as well, and
exactly as badly, as the record predicted.

### Issue #29 — a flaky test is a randomly refused pull request

`test_a_job_that_exceeds_its_memory_limit_is_killed_and_says_so` passed in CI at 12:35 and
failed at 12:44, on the same runner with the same tree: the container engine does not always
report `OOMKilled` when the kernel takes a process inside the container's cgroup, and exit code
137 on its own says nothing about who sent the signal.

**For Taktus this is not an ordinary flake.** P-03 runs at autonomy level 4 and its reason is
"the pipeline's verdict is the gate and never the worker's opinion". A verdict that is red at
random is not a verdict about the change. The test was **not** changed in this session, on
purpose: changing a test while a run waits on it is the shape of lowering a bar, even when the
change is right. The issue says what the right change is and why the obvious one — treating
exit code 137 as a memory kill — is worse than the fault.

### DEC-0025 — the description the repository would not accept

The first pull request Taktus opened was refused by its own pipeline: *no `## Decisions
required` section*. The checks that read a description run on the `pull_request` event and not
on a push, so the branch passed and the pull request did not — and P-03 cannot see the
difference, because it opens the pull request before that pipeline exists.

It took four attempts, and the lesson is a method one:

- **Attempt 4:** the body had none of the required sections. The template was asked to carry
  them and the worker to write its summary in the repository's shape.
- **Attempt 5:** the worker wrote a good description from the repository's own template — with
  `###` where the checks read `##`, and without `## Decisions required` at all.
- **Attempt 6:** that section moved into the template, with a sentence of explanation beneath
  it. The check accepts the single word `None`, and nothing else.
- **Attempt 7:** the section held only `None` — and the worker's body opens with a line of
  prose before its first heading, which fell into the section, because the check reads
  everything up to the next `## `.
- **Attempt 8:** a heading of its own closes the section. Green.

**Four of those five failures were deterministic things asked of a language model.** That is
the wrong method for them (ADR-0004), and this repository's own doctrine says so in CLAUDE.md
§3. What is fixed is now written by a `rule`; what is judgement is left to the model. One
deterministic piece is still the model's output — the generated block the owner reads — because
no connector operation reads a file of the repository. Issue
[#34](https://github.com/Jersyfi/taktus/issues/34).

## 5. What was slow, unclear, uncomfortable or surprising

**Slow.**

- The pipeline is 64 % of the run and is polled 22 times. An event would make it free in quota.
- One end-to-end attempt is about ten minutes, of which the part that does the work is two and
  a half. A defect met *after* the coding step costs a whole attempt to retry: the changeset is
  produced again from scratch, at full price, because the branch is the only place it was put
  and the branch is what has to be deleted.

**Unclear.**

- `worker.endpoint` is not in ADR-0002's isolation table, and until today nothing said that it
  isolates nothing. The bundle claimed isolation; the shipped command provided none
  (DEC-0022).
- A verdict of `changed` with the reason "no registered process uses this integration" reads
  like a finding and is the absence of one (issue #36).

**Uncomfortable.**

- **The estimate is a constant.** The worker returns the same five numbers whatever it is asked
  to do, and is honest about it (`confidence: low`). Everything downstream — admission today,
  the budget of `0.2.0` tomorrow — treats it as an estimate.
- **The coding worker ran with no isolation at all**, on the session's own machine, with the
  machine's whole network, while running an agent that writes and executes code. The frame
  named one allowed host and nothing enforced it. Nothing came of it. It should not be possible
  to arrive here by following the documented command, and now the command says so.
- **Seven branches were deleted by hand** during the running of a process whose whole point is
  that nothing is done by hand.
- **The resume that cannot resume.** The one situation a resume is for — the pipeline was wrong
  and is now right — is the one it cannot handle, because the read it verifies is already
  stored (issue #31).

**Surprising.**

- **The change was right every single time.** Eight independent runs of the same agent on the
  same brief produced eight correct implementations of issue #11. The variance was in cost, not
  in quality. Every failure of the day was Taktus's own.
- **The cheapest model did the judging step well.** P-02's criteria (DEC-0019) were seven
  testable items; the worker implemented six of them without argument, and the seventh — "the
  coding worker can rely on `make doctor`" — is not testable, and nobody pretended it was. No
  criterion had to be rewritten, which is the first entry in the quality history P-02's own
  `toward_next` asks for before its autonomy is raised.
- **The worker read the repository's rules when it was asked to, and not before.** `CLAUDE.md`
  was in front of it from the first attempt. It acted on the status rule only once an
  acceptance criterion named it. A rule that is written down is not a rule that is followed.

## 6. What the removal test shows now

Before today the removal test had run once, by hand, with one example process. `docs/status.md`
listed what was missing: *a removal-test verdict of `broke` on a real process*. Run again on
2026-09-23 with P-02 and P-03 registered:

| Integration | Verdict | What it rests on |
|---|---|---|
| `connector.channel.repo` | **broke** | **eight steps across both real processes** — `read-issue`, `read-comments`, `write-criteria`, `create-branch`, `wait-for-pipeline`, `read-pipeline`, `open-pr`, `label` — each with "no other adapter serves this capability and the step names no fallback" |
| `model.endpoint` | **changed** | P-02's `refine`: "no other adapter serves purpose reasoning; the step falls back to a person — the cost is a person's time, the quality theirs" |
| `persistence.database` | **exception** | ADR-0002's own reason: the one mandatory dependency, whose removal test is the restore drill |
| `worker.endpoint` | changed | "no registered process uses this integration" — see below |

**The missing verdict is no longer missing.** A `broke` on a real process, naming the steps, is
what the removal obligation of CLAUDE.md §6 asks for, and it is now in the ledger as
`removal.tested` and in the adapter's maturity.

**Three things it still does not show, and the first is the important one.**

- **It never actually ran anything.** Every real process of this repository writes outward, so
  the exercise **resolved** them statically — `not run: step(s) write-criteria would leave the
  system` — and rehearsed none. The rehearsal half of the removal test has still never happened
  against a real process and, on this repository, cannot: no process both uses an integration
  and writes nothing. W-12 and C-10 stay *pending* for the same underlying reason (DEC-0005).
- **No verdict of `changed` through an alternative adapter.** `changed` today means "falls back
  to a person", not "a second adapter did the job more cheaply or worse". That still needs a
  capability with two adapters, and nothing has one.
- **The `worker.endpoint` row says nothing and reads as though it did.** The instance was
  configured with the reference script worker, which serves none of the capabilities P-03's
  `implement` step requires, so no process "uses" it. With the coding worker configured the same
  identifier would give a different verdict, and neither the ledger entry nor the maturity
  record says which adapter stood behind the name. The weekly job runs against the reference
  worker, so its `worker.*` row will read this way every week. Issue
  [#36](https://github.com/Jersyfi/taktus/issues/36).

## 7. What this run proved, and what it did not

**Proved.**

- An issue of this repository becomes a pull request that passes CI, opened by Taktus, with a
  person deciding the merge. That is `0.1.0`'s completion criterion.
- The ledger chain and the provenance chain verify across 369 entries and eight runs, including
  runs that failed, escalated and were resumed.
- Every failure stopped at a step boundary with a reason. Nothing was left half done, no
  outward effect was repeated, and every `conflict` on a leftover branch was correct.
- Idempotency held: P-02's comment was written once and read by eight later runs, and a second
  P-02 pass refused itself.
- The coding worker ran against its real agent eight times, with tokens and money recorded per
  assignment.

**Did not prove.**

- **Anything about isolation.** The worker ran unisolated, by endpoint.
  `frame.allowed_hosts` was declared and not enforced. The `container` path exists and was not
  used here.
- **Anything about persistence.** The state was a file snapshot, not a database, and a restart
  at a step boundary was not exercised in this run.
- **Anything about the budget.** The estimate was a constant, the currency limit was a run
  limit five times the spend, and nothing was reserved at admission.
- **That the process is repeatable without a person.** Seven of eight attempts needed a hand
  between them, and the command that is supposed to run it cannot be run twice.
- **That the quality holds.** One issue, one day, one repository. P-02's `toward_next` asks for
  a month of criteria that nobody rewrote. This is day one of that month.

## 8. Everything this run turned into work

| Record or issue | What |
|---|---|
| [DEC-0020](../decisions/DEC-0020-a-branch-the-connector-writes-loses-the-file-mode.md) | the branch write dropped the file mode — corrected, with a test |
| [DEC-0021](../decisions/open/DEC-0021-must-a-taktus-pull-request-update-the-status-report.md) | must a pull request Taktus opens carry a status update? — **open**, issue [#27](https://github.com/Jersyfi/taktus/issues/27) |
| [DEC-0022](../decisions/DEC-0022-the-endpoint-worker-isolates-nothing-and-said-so-nowhere.md) | the endpoint worker isolates nothing, and the operator was not told — corrected |
| [DEC-0025](../decisions/DEC-0025-the-pull-request-taktus-opens-cannot-pass-the-description-checks.md) | the description the repository would not accept — corrected |
| [#28](https://github.com/Jersyfi/taktus/issues/28) | a new executable file still arrives plain |
| [#29](https://github.com/Jersyfi/taktus/issues/29) | the flaky memory-kill test |
| [#30](https://github.com/Jersyfi/taktus/issues/30) | `tools/first_run.sh` cannot be run a second time |
| [#31](https://github.com/Jersyfi/taktus/issues/31) | a resume cannot pick up a pipeline that turned green |
| [#34](https://github.com/Jersyfi/taktus/issues/34) | a generated section of the description is copied by a model |
| [#36](https://github.com/Jersyfi/taktus/issues/36) | the removal test's verdicts say too little about themselves |

Four further findings are in this record and are not issues, because they belong to work that
is already scheduled: the `llm` step admitted with no estimate, the model step whose money is
not reported, the worker's constant estimate, and the variance that makes a point estimate
useless. All four are the subject of `0.2.0`'s budget (ADR-0005), and the numbers above are
what it should be built against.
