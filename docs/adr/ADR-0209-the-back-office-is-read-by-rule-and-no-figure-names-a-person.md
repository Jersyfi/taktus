# ADR-0209 — The back office is read by rule, and no figure names a person

**Status:** accepted · extends ADR-0150, ADR-0024 and ADR-0015 (no assessment of a person) ·
issue #437, UC-03 B-5.01, B-5.03, B-5.04, B-5.05

## Context

UC-03 stage 1 asks four back-office processes. B-5.01 lists overdue tasks and reminds, counts
only by role. B-5.03 reviews access: inactive and over-privileged accounts marked; revoking
stays with a person. B-5.04 audits privileged actions by a rule on the action, never a learned
profile of a person (principle 14, DEC-0199). B-5.05 keeps the customer system: contacts and
touchpoints assigned, follow-ups proposed, duplicates merged by a person (UC-03 §4.5).

## Decision

### 1. Five capabilities

| Capability | Operations | Effect |
|---|---|---|
| `directory.accounts`, `directory.groups` | `.list` each | read over SCIM 2.0 (RFC 7643, RFC 7644): account id, user name, active, groups, roles, entitlements; groups with members; never a name, address or number |
| `audit.events` | `.list` | read: each event's moment, its hour in UTC, action, actor, target, whether it escalates rights; a count per action, never per actor |
| `tasks.items` | `.list`, `.read` | read: open tasks with due date and days overdue; never the assignee |
| | `.remind` | write, `marked`: a comment carrying the key, through which the tool notifies its assignee |
| `crm.contacts`, scoped to one address | `.find` | read: the contacts that carry the address |
| | `.create` | write, `marked` by the address itself |
| | `.note` | write, `marked` by the key: a touchpoint linked to the contact |

The actor of an audit event is kept, for the person who investigates. No step counts it.

### 2. The connectors

`scim/` over the open standard (`DIRECTORY_TOKEN`); `githubaudit/` over a repository service's
organisation audit log and `googleworkspace/` over a workspace's activity reports
(`AUDIT_TOKEN`); `linear/` and `jira/` in one shape (`TASKS_TOKEN`); `hubspot/` (`CRM_TOKEN`).
The audit log has a directory of its own: the repository connector is bound to one repository
and its app, the audit log to the organisation and an owner's token.

### 3. The processes

- **B-5.01**, level 2: one run per task a day overdue or more; a rule keeps a task on its first
  and seventh day overdue for a reminder, and from the seventh day the corridor
  `tasks.escalated` takes it to the tenant's role. Taktus addresses no person: the tracker
  notifies its assignee.
- **B-5.03**, level 1, monthly: a rule marks inactive accounts that still hold groups, and
  members of the group the tenant names privileged that are inactive or a service account.
- **B-5.04**, level 1, daily, rule only: an action of an escalating kind; an action outside one
  organisation-wide window of hours; one kind of action fifty times or more. No model.
- **B-5.05**, level 2: the sender of a mail is found by address, created when unknown, the
  touchpoint noted; a model proposes a follow-up as text for a person; two contacts with one
  address go to a person for merging. Nothing is sent.

## Alternatives

- **A learned profile of normal behaviour per person.** Forbidden by principle 14.
- **A reminder Taktus sends to the assignee.** It would need the person's address and make
  Taktus a monitor of people; the tool already notifies its assignee.
- **A merge of duplicates.** It cannot be undone in the customer system.

## Consequences

- Six connector directories, fakes, adapter tests and conformance entries.
- Four bundles, run in `tests/composition/test_software_operations_backoffice.py` and
  `test_software_operations_tasks.py`.

## Where this promise ends

- **SCIM has no last sign-in.** Inactive means `active: false` only; an account unused for a
  year and still active is not marked.
- **The organisation audit log is served only on the enterprise plan** of the repository
  service.
- **B-5.04's thresholds are literals of the bundle**, because a rule's bounds take no input; a
  tenant changes them in its own version. The window is one for everybody, in UTC.
- **"Now" for B-5.01 is the tracker's days overdue**, computed by the connector from the due
  date; no rule reads the clock.
- **Flagged messages are not listed**: the mail capability lists no flags.
- **A contact created is marked by its address only.** A repeat after somebody else created the
  same address reports it replayed.
- **Proven against fakes of the published APIs and of RFC 7644** (DEC-0225).
