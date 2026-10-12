<!-- The form of a product finding on the Taktus project's own instance (TAKTUS_FINDINGS_FORM, with TAKTUS_FINDINGS_LABELS=task): the sections of this repository's issue form `Task` (DEC-0051), so that its backlog reads a finding as any other task. Configuration of the project's tenant, not a default of the product (ADR-0092). -->
### What must be achieved

An instance of Taktus met something the product lacks. $tried The step failed for it, and its run waited until the step could start again.

The product offers `$lacking`, through an adapter or an operation of one it has, or this issue says why it does not.

### How it is verified

A step that needs `$lacking` runs on an instance with the product's adapters configured, and its block `$cause` is not met again.

### Where the boundary lies

Not support: this finding enters the backlog and is taken in its turn. Not repair: the instance reports, and the fix is a task of the product. Not a broken interface: an adapter that stopped behaving as expected is a failure, reported through the owner-facing channel.

### Component

$area

### Source

The blocked-time accounts of an instance: run `$run`, step `$step`, cause `$cause` (UC-6.12).

### Blocked by

nothing
