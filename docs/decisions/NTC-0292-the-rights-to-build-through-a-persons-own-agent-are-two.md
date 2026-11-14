# NTC-0292 — The rights to build through a person's own agent are two, and three acts wait for `confirm_act`

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** branch `area/conversation` of package F (concept mode, DEC-0222, DEC-0239)
**How it follows:** DEC-0239 item 5 lets a person's own agent plan, ask a change or a
description, rehearse and commission a proposal and roll back, "through the same services,
read-back and confirmation as the web app". It leaves open how the rights are cut and which
acts wait for a confirmation. ADR-0131 §3 cuts a right per kind of reach (start, answer,
take over); UC-7.3 grants every right to a role. Planning one's own draft and changing what the
tenant runs are two reaches, so they are two rights. Of the acts, the three that change a
process or start work at once are read back, as a decision's answer is (ADR-0131 §5).

## 1. What was decided

- Two rights, `agent.plan` and `agent.change` (ADR-0324 §2).
- `commission_plan`, `commission_proposal` and `rollback_process` come back read back and are
  done only by `confirm_act`; the other acts take effect at once, as on the web (ADR-0324 §3).

## 2. The evidence

- DEC-0239 item 5; UC-1.11 §2 as amended; ADR-0131 §3 and §5; UC-7.3.

## 3. What was considered

- **One right `agent.build`.** Rejected: an administrator could not let an agent plan a
  person's own work without letting it change the tenant's processes.
- **Every act read back.** Rejected: opening a draft or asking for a proposal changes no process,
  and the web does them at once; reading them back too would make the agent's path slower than
  the web's for no protection. Strict in substance where a process changes, sparing in ceremony
  elsewhere (CLAUDE.md §8).

## 4. Which entry permits it

None lists it; CLAUDE.md §8 lets the session decide an unlisted question from the sources and
record it here. The owner may overrule it in the pull request.

## 5. The entry it proposes

M1.30, a mode-1 entry: how the rights of a surface are cut follows the reach of the acts, one right per reach,
each granted to a role (ADR-0131 §3, UC-7.3).
