# NTC-0081 — A scheduled run acts for its activator

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#149](https://github.com/Jersyfi/taktus/pull/149), for issue #82

## 1. What was decided

A run a time trigger starts must act for someone (control-plane.md §2).

- **Old:** the scheduler asked the identity port for the sender `scheduler` on the channel
  `channel.schedule`, and the provisional operator identity of the tenant answered (DEC-0013).
  Without one, nothing fired.
- **New:** registering a process version records on the process the identity that registered
  it, `activated_by`. A schedule trigger of the active version acts for that identity, as the
  identity component places it when the trigger fires: the identity and its organisational path
  go into the command, the run and every connector call. A version registered by nobody, or by
  an identity the component does not know, fires nothing, and every tick says so in the log.
  ADR-0035 §6 is amended to say so (ADR-0040 §6).

## 2. The evidence

- `tests/composition/test_triggers.py`: a due trigger starts its run as the activator, whose
  path `t/ops` the command carries; an `each` read is called as the activator; a version
  registered without an identity, or by one the component does not know, starts nothing.
- `tests/integration/test_time_triggers.py`: two schedulers on PostgreSQL fire a version
  registered by `idn_scheduler` once per slot, and S-01 runs weekly from its trigger, as before.

## 3. What was considered

- **Link the scheduler's account to an identity, as a sender's.** A link is made by the person
  who holds an account, or by the organisation's source (UC-1.7). Nobody holds the scheduler's
  account, so it could be linked by neither.
- **Act as Taktus's own identity.** That identity is for what Taktus does on its own behalf
  towards a service (ADR-0033). A schedule runs a process on behalf of whoever commissioned it,
  as a command from any channel does for its sender.
- **A configured identity per tenant for schedules.** It would be the provisional identity
  again, under another name.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is issue #82, which removes
the provisional identity the scheduler used. The bundle format is unchanged; the process record
gains a field the registering identity fills; no limit, level or public statement moves.
