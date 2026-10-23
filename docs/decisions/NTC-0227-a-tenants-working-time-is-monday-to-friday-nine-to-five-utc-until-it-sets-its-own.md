# NTC-0227 — A tenant's working time is Monday to Friday, nine to five UTC, until it sets its own

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** issue [#430](https://github.com/Jersyfi/taktus/issues/430), in the pull request that implements ADR-0133
**How it follows:** UC-4.17 makes working time the tenant's configuration, never a person's, and names no value a tenant holds before it sets one. A deadline declared in working time must still fall due somewhere; leaving it without a due date would keep no deadline at all, which UC-4.17 §1 forbids. The default that is the tenant's to change, and the commonest working week, was taken. Where two defaults were both consistent with the source, the one that lets a deadline count at all from the first run was taken, strict in substance. This follows the precedent of NTC-0212 and NTC-0226 for a shipped tenant setting.

## 1. What was decided

A tenant that set no working time holds (ADR-0133 §4):

- **Zone:** UTC.
- **Working days:** Monday to Friday.
- **Working hours:** 09:00 to 17:00.
- **Holidays:** none.

`taktusctl deadline working-time --zone --days --hours --holiday` sets it. The default is
product, not the project's. A deadline declared in calendar time does not read it.

## 2. The evidence

- A working week of five days of eight hours is the most common one in the European Union, the
  frame of principle 11.
- UTC needs no time zone database, so the default counts on every instance, whatever its image
  holds. A zone such as `Europe/Berlin` is the tenant's to set.
- `tests/components/run/test_deadline_rules.py`
  `test_working_time_counts_only_the_tenants_hours` and `tests/composition/test_deadlines.py`
  `test_a_deadline_in_working_time_counts_only_the_tenants_working_hours`.

## 3. What was considered

- **No default: a deadline in working time does not start until the tenant sets one.** The
  deadline would be lost silently, as a timer is. Rejected (UC-4.17 §1).
- **Every hour is a working hour.** A deadline in working time would count as one in calendar
  time, and the declaration would mean nothing. Rejected.
- **The instance's own zone.** The zone of a server is no business's working time, and two
  instances of one tenant could differ. Rejected.

## 4. Which entry permits it

No entry of modes 3 or 4 names the default of a tenant's working time. M3.10 names limits on
spending; a working time spends nothing. No entry of mode 2 names it either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed covers it, widened by one example: **M1.24** — *The shipped default
of a tenant setting that limits no spending*: a grace period, a threshold for a report or a
stop, a window it is counted over, an interval of a recount, the working time a deadline counts
in, where the use case makes it the tenant's or the process's to set. Mode 1, because every
tenant can change it, and a limit on spending stays M3.10.
