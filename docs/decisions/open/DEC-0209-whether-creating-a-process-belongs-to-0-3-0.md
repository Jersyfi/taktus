# DEC-0209 — Whether creating a process belongs to 0.3.0

**Category:** NON-BLOCKING
**Mode entry:** none fits: M1.7 leaves a milestone's scope to the session, not its completion criterion, which the owner set (as in DEC-0207)
**Raised in:** the pull request that records it, on 2026-10-16, when every issue of `0.3.0` was closed
**Issue:** [#500](https://github.com/Jersyfi/taktus/issues/500)
**Needed by:** 2026-10-23
**Provisional answer:** Option A. The session moves the use cases no task builds to later milestones (M1.7) and verifies what `0.3.0` built on the instance; the milestone stays open until the answer.

## 1. What this is about

Every issue of `0.3.0` is closed, 38 of 38. Its completion criterion says: "a process can be created, viewed, changed and rolled back entirely from the web app and chat, and you can see your own share of the waiting time."

What was built:

- **viewed:** the four levels, live (UC-6.10);
- **changed and rolled back:** in dialogue, from the web app and the chat (UC-4.15, #294 to #299);
- **your own share of the waiting time:** the web app's view of one's own decisions.

What was not built is **created**. UC-4.1, "a process from a description", is `specified` and no task builds it. Seven more use cases carry `0.3.0` as their version without a task, and none of them is in the criterion: UC-1.4, UC-1.5, UC-1.8, UC-4.2, UC-5.5, UC-6.5 and UC-10.2.

## 2. Why you are being asked

The completion criterion is the owner's (DEC-0207 answered the same question for `0.2.0`). Which use case lands in which milestone is the session's (M1.7), so the seven outside the criterion are moved by the session.

**Sources checked:**

- the vision: principle 2 asks for processes from descriptions, but says nothing of their milestone;
- the ADRs: ADR-0091 (changing a process) bounds UC-4.15, not when UC-4.1 is due;
- the roadmap's `0.3.0`;
- M1.7 and the rest of both anchor pages;
- DEC-0186 (what changing a process must do, answered provisionally as UC-4.15);
- DEC-0207;
- the use cases' states (`make usecases`) and the issues that name them.

## 3. What you must decide

Whether `0.3.0` completes without "created", which then moves with UC-4.1 to a later milestone, or stays open until UC-4.1 is built.

## 4. What you need to know to decide

- UC-4.1 is a process drafted from a description in words. No issue builds it.
- A process can be *changed* in dialogue today: UC-4.15, with `TAKTUS_CHANGE_PROCESS` naming the process that turns words into a proposal. Creating one from nothing is UC-4.1's.
- Building UC-4.1 means planning tasks first, the way #294 to #299 were planned for UC-4.15: by that measure, one to two weeks.
- `0.4.0` is the ML bench and the second tenant, whose stage 1 needs processes made for a business. UC-4.1 serves that.

## 5. Options

### Option A — `0.3.0` completes without "created"; UC-4.1 moves to `0.4.0` (recommended)

- **Meaning:**
  - the criterion becomes "a process can be viewed, changed and rolled back entirely from the web app and chat, and you can see your own share of the waiting time";
  - "created", with UC-4.1, moves to `0.4.0`;
  - the session verifies what was built on the instance before it closes `0.3.0`.
- **Consequence:** `0.3.0` closes within days. UC-4.1 is planned where the second tenant needs it.
- **Effort:** the roadmap's sentence, the use cases' versions, and a check on the instance.
- **Reversibility:** a later answer moves it back.
- **Why recommended:** the criterion's other four parts are built. The missing one belongs to the work that needs it.

### Option B — keep "created" in `0.3.0`

- **Meaning:** UC-4.1 is planned and built before `0.3.0` closes.
- **Consequence:** about one to two weeks more for `0.3.0`.
- **Effort:** the tasks of UC-4.1.

## 6. What is blocked

Closing `0.3.0` on the host. Nothing else.

## 7. How to answer

In #500: "DEC-0209: Option A" or "DEC-0209: Option B".
