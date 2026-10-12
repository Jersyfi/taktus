"""What a proposed version changes against the version it was made against, by a rule
(ADR-0091 §1). Pure: two versions in, their difference out.

Steps are matched by their identifier. A step only in the proposal is added, a step only in the
base is removed, and a step in both whose fields differ is changed, with the fields named. The
work a step does when it runs counts as a field of its own, `work`.
"""

from __future__ import annotations

from taktus.components.process.domain.model.process import ProcessVersion
from taktus.components.process.domain.model.proposal import Difference, StepChange


def difference(base: ProcessVersion, proposed: ProcessVersion) -> Difference:
    before = {step.id: step for step in base.steps}
    after = {step.id: step for step in proposed.steps}
    changes: list[StepChange] = []
    for step in proposed.steps:
        old = before.get(step.id)
        if old is None:
            changes.append(StepChange(id=step.id, change="added", after=step))
            continue
        old_fields, new_fields = old.document(), step.document()
        fields = [
            name
            for name in sorted(set(old_fields) | set(new_fields))
            if old_fields.get(name) != new_fields.get(name)
        ]
        if base.work.get(step.id) != proposed.work.get(step.id):
            fields.append("work")
        if fields:
            changes.append(
                StepChange(
                    id=step.id, change="changed", before=old, after=step, fields=tuple(fields)
                )
            )
    changes.extend(
        StepChange(id=step.id, change="removed", before=step)
        for step in base.steps
        if step.id not in after
    )
    return Difference(
        steps=tuple(changes),
        autonomy_before=base.autonomy,
        autonomy_after=proposed.autonomy,
        triggers_changed=base.triggers != proposed.triggers,
        inputs_changed=base.inputs != proposed.inputs,
    )
