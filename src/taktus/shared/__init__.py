"""The shared kernel: the concepts every part of Taktus agrees on, bound to Python.

The kernel itself is language-neutral JSON Schema under contracts/shared (ADR-0016). This package
is its Python *binding*: one frozen Pydantic model per schema, mirroring the schema's properties,
required fields, enumerations and rules. The binding is hand-written and machine-checked, not
generated: tests/contract/test_shared_kernel_binding.py reads every schema and fails on any
difference in shape, and runs every example of the contract through the models. A field that
exists here and not in the schema, or the other way round, is a failing test, not a drift.

Why a checked binding and not generation: the schemas carry rules (`if`/`then` over the method of
a step, "at least one quantity") that no generator turns into a Python validator, and the
components need exactly those rules in the constructor (docs/architecture/project-structure.md
§4). Generating the shape and hand-writing the rules would have been two files per concept with
the seam in the wrong place.

Everything the components share travels as one of these types. No component imports another's
classes; what they exchange is here (ADR-0016).
"""
