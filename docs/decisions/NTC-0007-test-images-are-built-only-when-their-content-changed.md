# NTC-0007 — Test images are built only when their content changed

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-09-30
**Raised in:** PR_LINK

## 1. What was decided

Every image the tests run — the reference worker, the control plane, the memory test's unit — is
built through one helper. It labels the image with a digest of its Dockerfile and every file it
copies, and calls no build at all when an image with that digest exists. A needed build writes
its progress to a log; a build silent for 120 seconds, or past its bound, is stopped, and the
first test that needs it fails naming the image, the step it stopped in and the log. `make
images` builds them ahead.

## 2. The evidence

The seven errors of 2026-09-29 (DEC-0036): two `docker build -q` runs hung for 600 and 900
seconds without a line of output, and pytest repeated the cached fixture error for seven tests.
Cold builds take 1 to 23 seconds on the same machine. After the change a healthy `make gates`
costs the same (220 s before, 224 s after); image fixtures with their images present take 0.0 to
0.1 s instead of 0.5 to 0.8 s, and a hang costs 120 s naming its step instead of 600 or 900 s
naming nothing.

## 3. What was considered

- Raising the timeouts: rejected by the owner's rule; it makes a hang cost more and say nothing.
- Marking the container tests to run only in CI: rejected, the tests pass locally whenever the
  builder does, and they are the only local proof of the isolation.

## 4. Which entry permits it

M2.2: how the tests obtain their images is test strategy; every test still runs, locally and in
CI, and none is weaker.
