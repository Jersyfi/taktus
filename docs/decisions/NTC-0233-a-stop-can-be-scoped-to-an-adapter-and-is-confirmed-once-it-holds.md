# NTC-0233 — UC-7.2: a stop can be scoped to an adapter, and is confirmed once it holds

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-23
**Raised in:** this pull request, for #436
**How it follows:** the owner accepted the second tenant's catalogue as the requirement Taktus proves itself on in DEC-0199 (Option A, "fully supported by `1.0.0`"). The catalogue asks for "a stop per agent and global, with confirmation" (`docs/usecases/AF-03-software-operations.md`, B-11.04 and §7 row 6), and maps it to UC-7.2. UC-7.2 stopped globally, per tenant, process or run, and said nothing of a confirmation. The amendment states the two missing parts as UC-7.2's requirement, with the verification conditions of #436.

## 1. What was decided

UC-7.2 §1 gains two paragraphs, §2 two conditions:

- **The adapter scope.** A stop may be scoped to an adapter. It stops every step that adapter
  serves, in every run, and nothing else; runs on other adapters go on. The catalogue's *agent*
  is read as an adapter — a worker, a connector or a model — because that is what acts in a step
  (CLAUDE.md §6). The verification names a worker adapter, as #436 does.
- **The confirmation.** A stop is confirmed once it holds, when every affected run has reached
  its boundary. The confirmation goes to whoever requested the stop and names the runs it
  stopped. A stop that found no run is confirmed too, and says so: otherwise the person cannot
  tell an empty stop from one that never held.

§4 names the source, §5 what is not built. §3 is unchanged: the automatic trigger and the resume
stay outside, as #436 says.

## 2. The evidence

- DEC-0199, *Outcome*, points 2 and 5 of how the session reads the answer.
- `docs/usecases/AF-03-software-operations.md`, B-11.04 and §7 row 6, which already name
  UC-7.2 and #436.
- Issue #436, *How it is verified* and *Where the boundary lies*.

## 3. What was considered

- **A new use case.** Rejected: the stop, its scopes and its boundary are UC-7.2's; a second use
  case would split one requirement in two.
- **An agent as a process.** Rejected: a stop per process already exists. The catalogue lists
  "one process, an adapter or everything" as three scopes.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the catalogue the
owner accepted in DEC-0199. The owner may veto it within seven days of this pull request; a veto
turns it into a request under M3.15.
