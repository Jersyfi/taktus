# NEED-0028 — The second tenant's systems, volumes and roles

**Kind:** information
**Raised in:** the pull request that records DEC-0199
**Issue:** [#426](https://github.com/Jersyfi/taktus/issues/426)
**Needed by:** 2026-10-31
**Foreseeable since:** DEC-0199, the day the business's catalogue arrived without the systems it uses

## 1. What is needed

The business that becomes Taktus's second tenant sent a catalogue of what it needs. It does not
say which systems the business uses, how much arrives, or who decides. Five answers are needed
from the business, through you:

1. **Systems.** For each capability in the table of `docs/usecases/AF-03-software-operations.md`
   §8, the system the business uses for it, or "none".
2. **Volumes.** Roughly how many arrive per week: incoming messages, support requests, new
   errors, payments, invoices, pull requests.
3. **Roles.** Who releases money, who answers legal matters, who approves which classes of reply,
   who reads the daily report. Roles first; one contact person for decision requests.
4. **Where its data may go.** Whether the tenant runs on your instance beside the project's
   tenant, or on an instance of the business's own; and which model providers may receive its
   data.
5. **Additions.** Anything the business wants to keep with a person beyond the catalogue's list,
   and any threshold it wants stricter.

## 2. Why

Processes name capabilities, never products. A connector for a capability can only be chosen
or built once the system behind it is known. Stage 0 of UC-03 needs error tracking, mail and
the repository service; stage 1 needs cloud billing, payment providers and the model
providers' credit. #400 cannot register the tenant's processes without the roles and the place
it runs.

## 3. By when

**2026-10-31**, the date NEED-0027 set for starting #400.

If it is not there by then, #400 starts stage 0 with the two capabilities Taktus already has,
the repository service and chat: the daily report on pull requests and pipelines, and the
routines for pull requests. The other processes wait for this need.

## 4. How to provide it

1. Ask the business for the five answers.
2. Write them into a private note outside the repository: `~/Dev/taktus-private/second-tenant.md`,
   beside the note on the platform. Names of systems belong there, never in the repository.
3. Answer in the issue with the sentence "NEED-0028: in the private note". Nothing else goes into
   the issue.

No credential is needed yet. Each connector raises its own credential need when it is built,
through `CREDENTIALS.md`.

## 5. What it must never be

Never the business's name, a system it uses, a volume, a role holder's name or an address in
this repository, an issue, a pull request, a log or a message to a session's model provider
beyond what the work needs. The answers go into the private note only. A session reads them
there and writes the tenant's configuration into the tenant's instance, never into a file here.

## 6. What happens next

Tell the session "NEED-0028: in the private note". It reads the note, configures the tenant on
its instance (#318), raises one credential need per connector stage 0 needs, and starts #400.

## 7. How to confirm

```bash
test -s ~/Dev/taktus-private/second-tenant.md && echo present
```

The command prints `present` without printing the content.
