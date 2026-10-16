# NEED-0030 — The coding agent's API workspace limit for October

**Kind:** action
**Raised in:** the pull request that records it, on 2026-10-16
**Issue:** [#490](https://github.com/Jersyfi/taktus/issues/490)
**Needed by:** 2026-10-18
**Foreseeable since:** 2026-10-16 16:36, when the coding step of `run_797eaf7d2abec09b62f0` was answered "You have reached your specified workspace API usage limits. You will regain access on 2026-11-01 at 00:00 UTC."

## 1. What is needed

The usage limit of the API workspace that the coding agent's key (NEED-0001, renewed under NEED-0005) belongs to is raised for October, or the owner decides that coding waits until 2026-11-01.

## 2. Why

Every coding step of Taktus's instance stops on that limit:

- stage 0's tasks: #471 and #481 were given back on it, and #472 waits;
- the live run of #74 (DEC-0206).

The owner raised the limit to USD 50 on 2026-10-14. On the instance, the priced coding steps of the last 72 hours spent USD 21.39. One run of 2026-10-14, before steps were priced, used about USD 10. The rest of the limit was spent outside the instance's runs, by uses of the same workspace that Taktus does not record.

## 3. By when

**2026-10-18.** Each day without it is a day stage 0 measures nothing, and `0.2.0` completes only after stage 1 has run two weeks (DEC-0207).

## 4. How to provide it

1. In the provider's console, open the workspace the instance's key belongs to, then *Limits*.
2. Raise the monthly usage limit. USD 100 leaves about USD 50 for the rest of October: stage 0's remaining tasks at USD 1 to 3 each, and #74 under its USD 5.
3. Say so in #490. The session switches P-03 on again and hands the waiting tasks over.

## 5. What it must never be

- Never a second key put in place of the instance's to get around the limit.
- Never a limit removed altogether: the workspace limit is the last bound behind P-03's USD 5 per run.

## 6. What happens next

The session switches P-03 on, which it switched off on 2026-10-16 for #74's run. It hands over #471, #472 and #481 again, runs #74 under its USD 5, and watches the spend daily.

## 7. How to confirm

A coding step finishes on the instance again. The session records it in #490.
