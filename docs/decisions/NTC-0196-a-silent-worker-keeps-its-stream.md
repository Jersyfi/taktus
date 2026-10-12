# NTC-0196 — A silent worker keeps its stream

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** issue [#271](https://github.com/Jersyfi/taktus/issues/271), in the pull request that closes it

## 1. What was decided

The worker client reads a stream until `assignment.finished`, as before, with three changes:

1. **A silence is not a break while the worker works.** When no event arrives within the idle
   timeout, the client asks the worker for the assignment's state. When the worker answers and
   the assignment has not finished, the client reconnects and the silence costs no attempt.
2. **Attempts are counted between two events.** An event resets the count, so an assignment
   with several silences is not cut off at the third.
3. **The whole stream is bounded.** `stream_timeout` (3 600 s by default) was declared and never
   checked; a stream that has not finished by then is a WorkerError.

A worker that is gone — its state does not answer — or whose assignment finished without the
event ends the stream after the configured attempts, as before.

## 2. The evidence

- `tests/adapters/workers/test_http_stream_silence.py`: five silences of a working worker read
  to the end; a gone worker and a finished assignment still end after the attempts; a stream that
  never finishes ends at its bound.
- The live run of #74 on 2026-10-12, whose coding step failed after seven minutes of work and
  about USD 1 while the worker still ran.

## 3. What was considered

- **A heartbeat in the worker contract.** It would make every worker send something it does not
  need to, and change a contract a third party implements; the state the contract already offers
  answers the same question.
- **A longer idle timeout.** It moves the line without removing it: a test suite that runs longer
  is cut off all the same, and a worker that is gone is noticed later.

## 4. Which entry permits it

M2.4: what the client does changes inside the worker contract; no contract, limit or level moves.
