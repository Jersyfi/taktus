# DEC-0036 — `make gates` was not green in one command on the owner's machine

**Category:** DEFECT
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51), which diagnoses the seven errors and removes their cause
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Since the first pull request the repository has promised that `make gates` is green from a
clean clone in one command (`tools/README.md`). On 2026-09-29 the owner's machine ran it and
`make test` ended with seven errors after 26 minutes, while CI passed. The promise was not true.

Each of the seven errors, read from the log of that run: every one is a test's setup failing
with a timeout of `docker build -q`, with no output at all.

- **Five errors, one build.** `taktus-worker-script:test` hung for its full 600 seconds. Its
  fixture is shared by the whole session, so pytest reported the same failure again for four
  more tests: three in `test_container.py`, one in `test_control_plane_image.py`, one in
  `test_launched_container.py`.
- **Two errors, one build.** The control plane image hung for its full 900 seconds; its
  "retry once" did not apply, because it caught a non-zero exit and not a timeout.
- **Between them**, the memory test's own image built normally, and a later run in the same
  place passed in 101 seconds. Cold builds measured on the same machine take 1, 14 and 13
  seconds.

The builds were not slow; they hung, and `-q` discarded the progress that would have said
where. 600 + 900 of the run's 1,566 seconds were the two hangs.

## 2. Why you are being asked

You are not. The repository said something untrue about itself, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`. The correction removes the cause and raises no timeout.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- **A rerun needs no build at all.** Every image the tests use is built through one helper
  (`tests/images.py`) and labelled with a digest of its Dockerfile and every file it copies. When
  an image with that digest exists, `docker build` is not called, so neither the builder nor a
  registry is asked.
- **A hang says where it hung.** A needed build writes its full progress to a log. A build silent
  for 120 seconds, or past its bound, is stopped. The first test that needs it then fails, naming
  the image, the step it stopped in, the last lines and the log. Every later test says so in one
  line.
- **`make images`** builds them ahead.
- **Cost before and after** on this machine: a healthy `make gates` 220 s before, 224 s after,
  the same within noise. Image fixtures with the images present take 0.53–0.81 s per image
  before, still contacting the builder, and 0.0–0.1 s after. One hung build cost 600 or 900 s
  with no hint before, and 120 s naming the step after.
- **What was not found.** Why the builds hung is not in the log, because nothing was printed.
  The next hang will say which step it stopped in.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0036" in an issue.

## Outcome

**Corrected:** 2026-09-30
**What was wrong:** `tools/README.md` said `make gates` is green in one command; on the owner's
machine it was not, and its seven errors named no cause.
**Why it was wrong:** every test session rebuilt every test image through a quiet `docker build`
with a long timeout, so a builder that hung cost ten or fifteen minutes and said nothing.
**What it now says:** the gates are green in one command again; a test image is built only when
its content changed, and a build that hangs fails naming where.
**What changed in substance:** the tests' image fixtures and `make images`; no gate was weakened
and no timeout raised.
**Recorded in:** [#51](https://github.com/Jersyfi/taktus/pull/51)
