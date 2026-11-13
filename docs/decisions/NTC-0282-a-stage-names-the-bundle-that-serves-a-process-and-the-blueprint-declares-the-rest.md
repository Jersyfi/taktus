# NTC-0282 — A stage names the bundle that serves a process, and the blueprint declares the rest

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** branch `area/ops2` (final round before 1.0, concept mode, DEC-0236)
**How it follows:** ADR-0191 §1 opens a stage only once every process it adds runs for the
tenant. ADR-0191 §4 names a process by its bundle's identifier. `stages.yaml` named `b-7-02` and
`b-7-03`, which no bundle carries. The bundles that serve B-7.02 and B-7.03 are the
dev-orchestration blueprint's `p02-refinement` and `p03-implementation`, as the blueprint's
README already said. So stage 4 could never count their runs. Naming the serving bundle follows
ADR-0191 §4 as written. NTC-0263 is the precedent for processes that are part of another: a
tenant's plan names the bundle that serves them. Strict in substance, sparing in ceremony: the
mapping is declared once, in the blueprint, and a test holds it.

## 1. What was decided

- Stage 4 of `blueprints/software-operations/stages.yaml` names `p02-refinement` and
  `p03-implementation` in place of `b-7-02` and `b-7-03`.
- `blueprint.yaml` declares every process of UC-03 that has no bundle in the blueprint. Each
  declaration either names the bundles that serve the process (`served_by`), or names none where
  the instance itself does the work for every process, or says `not_built: true`. Every
  declaration gives its reason. Nothing is proposed for these processes.
- The processes without a bundle are those that need documents or master data only the business
  holds (B-9.05, B-10.05 to B-10.07), those with no public source (B-9.08), and the others
  UC-03 lists that no interface reaches (B-2.06, B-4.07, B-6.05). They are limits in the
  README's *State* table (DEC-0225), not fakes.

## 2. The evidence

- `tests/governance/test_stages.py`,
  `test_every_process_a_stage_names_is_a_bundle_or_declared_where_it_is_served`. It checks that
  every process a stage names is carried by a bundle of some blueprint or declared without one.
  It checks that nothing declared has a bundle here. It checks that every serving bundle a
  declaration names exists.
- `tests/composition/test_software_operations_chain.py` runs B-3.06, B-7.01, P-02, P-03, B-7.05
  and B-7.12 as one chain.

## 3. What was considered

- **Bundles `b-7-02` and `b-7-03` that wrap P-02 and P-03.** Rejected. They would be a second
  copy of two processes the dev-orchestration blueprint already ships, and the two copies would
  drift apart.
- **A mapping inside `stages.yaml`.** Rejected. The stage file's schema is the governance
  component's, and it admits no extra key. The blueprint file is where an instance reads its
  processes.

## 4. Which entry permits it

M2.6, with NTC-0263 as precedent. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond M1.1, naming and placement: which identifier a stage names a process by is naming,
and ADR-0191 §4 already fixes it.
