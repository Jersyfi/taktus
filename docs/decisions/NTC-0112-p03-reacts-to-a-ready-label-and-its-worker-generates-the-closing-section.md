# NTC-0112 — P-03 reacts to a ready label, and its worker generates the closing section

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#77](https://github.com/Jersyfi/taktus/issues/77), in the pull request that closes it

## 1. What was decided

- **P-03 Implementation** (version 5) carries the trigger of the blueprint's `issue.ready`:
  `issue.labelled` with the filter `label: ready` and the condition `capacity.available`. The
  trigger gives this repository's records directory, the clone, its host and the name of the
  coding worker's credential; the issue comes from the event. Until now P-03 had no trigger and
  started only by hand (NTC-0103).
- Its worker step runs `python3 tools/check_status.py --print` after the work, in its workspace,
  and publishes what it printed as the artifact `closing` (ADR-0053). A new template step,
  `closing-section`, puts that under the heading `## Needed from the owner`.
- The input `closing_section` is optional. The description ends with it where whoever started
  the run gave it, as before, and with the worker's section otherwise.
- A bundle may declare an input `required: false`, and a reference to it names what stands in
  for it under `$otherwise`. `taktusctl run` asks only for the required inputs, and a trigger
  must give only those.
- Both reference workers run a task's command after the work, and the conformance suite checks
  it as W-18.

## 2. The evidence

- `tests/integration/test_implementation_on_an_event.py`: an issue labelled `ready` starts P-03
  through the daemon's automation role with no `closing_section`, and the run opens a pull
  request. Its last section is byte for byte what `tools/check_status.py --print` prints on the
  pull request's branch, read back from the hosting service, and the description check passes
  there.
- `tests/integration/test_dev_orchestration.py`: the manual start with `closing_section` still
  ends the description with what it was given.
- `tests/conformance`: both reference workers pass W-18; a worker that ignores the command fails
  exactly W-18; the fixtures `W-18-*` fail the stream rule.
- `tests/components/process/test_event_triggers.py`: P-03 as shipped registers with its trigger,
  which gives every required input and not `closing_section`.

## 3. What was considered

- **Remove the input `closing_section`.** Rejected: the issue's boundary keeps it for the manual
  start.
- **Leave P-03 without a trigger and start it by an event only in the test.** Rejected: the
  trigger is what DEC-0050 deferred to this change, and NTC-0103 kept it out for
  `closing_section` alone.
- **Take the clone's address from the event.** The event carries the repository as
  `owner/name`, without a host, so the trigger names the clone. It is this public repository's
  own address, not a deployment's.

## 4. Which entry permits it

M2.4, inside the scope of issue #77, which carries DEC-0037's answer: the session decided Option A
under M1.11, and that answer named the worker contract's optional command after the work. No
limit or autonomy level moves; P-03 stays at level 4, and the contract's `v1` has not been
released (ADR-0019). Whether P-03 runs on an installed instance is the deployment's: no instance
runs the automation role yet.
