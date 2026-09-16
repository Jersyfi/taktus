"""The composition root: where ports meet adapters and the roles are assembled.

Nothing here has business logic. It chooses which adapter stands behind which port for one
way of running Taktus, builds the application services with them, and starts a driving adapter.
It is the only package that may import everything (docs/architecture/project-structure.md §3).
"""
