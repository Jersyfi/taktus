# ADR-0020 — Tenants and instances are different boundaries

**Status:** accepted

## Context
Two words are used for "keeping things apart" and they are easy to confuse. Confusing them leads
to the wrong deployment later: either every department gets its own database and nothing can be
shared or compared, or the project that develops Taktus and the project that depends on Taktus
end up in one database, and a faulty build takes down productive work.

Persistence arrives now (ADR-0013 A). Every table is created with its boundary column from the
first migration, because a column added later means rewriting every query and every test. So the
two boundaries have to be named before the schema exists.

## Decision

### 1. Two boundaries
A **tenant** separates organisational units *inside one running instance*: departments, teams,
projects, a family. A tenant governs visibility, sharing, cost attribution and permissions. Every
row in the database carries its tenant, and row-level security in the database keeps tenants
apart even when a query forgets the filter.

An **instance** separates *deployments* with a different cadence and a different blast radius. An
instance has its own database, its own secret store and its own configuration. Two instances share
nothing.

The two axes are independent. One instance can hold many tenants. One organisation can run several
instances.

### 2. The Taktus project runs two instances
- The **development instance** runs `main` and develops Taktus.
- A **project instance** runs a tagged release and manages one product.

Three reasons:

1. A faulty version built by self-development must not take down the instance doing productive
   work. One instance builds the version, another runs it. That satisfies ADR-0013 D by
   construction rather than by discipline.
2. The two need a different cadence. Development must carry the newest state. Production must
   not.
3. Running a project instance is the same path an external operator walks. It is the only way to
   find out where that path is uncomfortable.

### 3. Hard rules between instances
- No shared database.
- No shared secret store.
- No connection between instances. A project instance never calls the development instance and
  does not know that it exists.
- No Taktus code, configuration or dependency is ever placed in a managed repository. The
  instance runs *beside* the project, never *inside* it.

### 4. What the rules mean for the code
- Every table carries a `tenant` column, and every repository call names its tenant as an explicit
  parameter, never as a default. Row-level security policies enforce the boundary in the database.
- Until the identity component exists, one tenant named `default` is created by migration.
- An instance is configured through its environment (`TAKTUS_*`); nothing in the repository names
  a particular instance.
- The hash chain of the ledger (ADR-0006) is one chain per tenant. A tenant can verify its own
  chain without seeing another tenant's entries.

## Alternatives
- **One instance for everything, tenants only.** Simpler to operate, and exactly the failure ADR-0013
  D exists to prevent: the version under development and the version doing the work would share
  one process and one database.
- **One instance per tenant.** Every department a deployment of its own; nothing shared, nothing
  comparable, and the smallest installation (ADR-0002) becomes several installations.
- **Adding the tenant column later, when identity exists.** Every query, every migration and every
  test written until then would be rewritten.

## Consequences
- The schema starts with the tenant column and row-level security; the identity component later
  fills the tenant table rather than retrofitting the boundary.
- The project's own operating documentation describes two installations, not one.
- A release that Taktus builds is proven on the development instance and deployed to a project
  instance by a person or by another instance (ADR-0013 D).

## Where this promise ends

Row-level security keeps tenants apart inside the database for the application role; a
superuser and a backup file see everything. Two instances share nothing by rule; the rule is
applied by whoever configures them, and nothing in Taktus can detect that two instances were
pointed at one database. One tenant, `default`, exists until the identity component does
(`0.2.0`); until then the tenant boundary is real in the schema and trivial in use.
