# DEC-0123 — No figure compares the working time of named persons

**Category:** NON-BLOCKING
**Mode entry:** M4.5
**Raised in:** the session's explanation of DEC-0069, DEC-0082 and DEC-0087 on 2026-10-10, where the owner's idea of measuring working time met principle 14; recorded in the pull request that records the owner's answers of that day
**Issue:** none; the owner answered in conversation before a request was written, and this record is the question with the answer
**Needed by:** 2026-10-10
**Written after the answer:** the owner answered in conversation on 2026-10-10; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Asked to explain the requirements of the second to fourth migration steps again, the owner
described how they want people's work in a process measured. The time from a step's start to its
end is taken. The person also records the time they actually worked on it. The difference is
time lost in the process. Over many runs this shows how long a step usually takes. It would also
show where a person takes longer than others, so that they can be supported.

The first two parts are process analysis. The third compares named persons. Principle 14 forbids
that: "any metric that appraises a named person" and "a ranking of people" — and it says such a
feature is unbuildable, not merely switched off.

## 2. Why you are being asked

Entry M4.5 of `docs/decisions/anchors.taktus.md`: the vision layer, the fourteen principles and
what they forbid, is the owner's. Measuring individuals against each other would change what
principle 14 forbids.

**Sources checked:** principle 14 forbids the comparison and permits aggregation by role or
department; ADR-0015 puts it in the data model; ADR-0043 already books blocked time by cause and
duration and keeps a wait on a person readable by that person alone; UC-6.4 refuses a view that
groups figures by person. None of them can change a principle; only the owner can.

## 3. What you must decide

May Taktus show a comparison of the working time of named persons, to support the slower ones?

## 4. What you need to know to decide

- **What stays possible either way:** the lead time and the working time of every step, the
  time lost between them, and how both vary — per process, step, role and department, in as
  much detail as the data allows.
- **A person's own times** can be shown to that person, next to the average of their role.
- **In Germany**, a technical system able to monitor behaviour or performance at work generally
  requires the works council's co-determination, and the GDPR applies to the data. This is
  context, not legal advice.

## 5. Options

### Option A — principle 14 stands; support starts with the person

- **Meaning:** every person sees their own times and the average of their role, and can ask for
  help. Managers see where in a process times vary widely and improve the step's instructions or
  training for the whole role. Nobody sees who is slower.
- **Consequence:** no change to the vision or to any use case.

### Option B — comparing persons is allowed for support

- **Meaning:** principle 14 is changed. A manager sees which person stands out.
- **Consequence:** the vision, ADR-0015, UC-6.4 and UC-8.5 change; the trust principle 14 protects
  is at stake, and co-determination and data protection apply.

### Option C — the owner's own wording

## 6. What is blocked

Nothing. The use cases already follow Option A.

## 7. How to answer

"DEC-0123: Option A.", "DEC-0123: Option B." or the owner's own wording.

## Outcome

**Decided:** 2026-10-10
**Answer:** Option A. Principle 14 stands. Support starts with the person; nobody sees who is slower.
**Reasoning given:** the owner's, in conversation: it is about people in a process, and Taktus is
built to European norms and ethical principles. That has to go together with an open culture
towards mistakes — handling them well when they are made, and striving to improve. To shape
processes so that they are economically sustainable and keep improving them, the processes must
be analysable in every detail, so that potential for improvement is found and, for example,
wasted time eliminated.
**Recorded in:** this pull request; principle 14 carries the owner's reasoning as what it permits.
