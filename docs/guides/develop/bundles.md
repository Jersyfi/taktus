A **process** is recurring work, described as steps. It is written in a YAML file called a
**bundle**. Registering a bundle stores it as a **version** of the process; a **run** is one
execution of that version.

## What every step states

Each step chooses one **method** of eight: `rule`, `statistics`, `ml`, `neural`, `llm`, `worker`,
`human`, `wait`. The first four are reproducible: the same input gives the same result. A step
also states why:

| Field | What it says |
|---|---|
| `method` | how the step is done |
| `reason` | why that method suits the step |
| `rejected` | the methods considered and not chosen, each with `why` |
| `exactness` | how exact the result must be: `exact`, `sourced`, `tolerant` or `free`; a `wait` or `human` step produces no result and carries none |
| `checks` | how the result is checked; an `exact` or `sourced` step needs at least one |
| `fallback` | where the step goes when its method fails; required for `llm` and `worker`, and it names a role, never a person |
| `work` | what the step does when it runs |

An `exact` result is produced only by `rule` or `statistics`. A language model may prepare it,
never produce it.

Every bundle also carries `takeover`: how a person does the work without Taktus, step by step.
A bundle without it does not register.

## A minimal bundle

A note for the team every Monday. A language model drafts it, and a rule signs it.

```yaml
id: weekly-note
version: "1"
name: Weekly note
autonomy:
  level: 2
  reason: a person confirms each step before it starts, until the note has proven itself
  toward_next: ten runs in a row in which nobody corrected the note
author: the team
reason: the team receives one short note at the start of every week

limits:
  compute: { seconds: 30, resource_class: cpu.small }

triggers:
  - schedule: weekly

steps:
  - id: draft
    method: llm
    reason: a short, friendly text is a language model's strength
    rejected:
      - method: rule
        why: a fixed text reads the same every week and is skipped
    exactness: free
    fallback:
      when: the model fails or its answer does not match the pattern
      to: human
      role: team-lead
    work:
      purpose: writing
      prompt: Write two sentences that open the team's week. No names, no dates.
      max_output_tokens: 200
      pattern: "\\S"

  - id: sign
    method: rule
    reason: the signature is fixed; nothing here needs judgement
    rejected:
      - method: llm
        why: a fixed text needs no language model
    exactness: exact
    checks:
      - { kind: recomputation, subject: the signed note }
    depends_on: [draft]
    work:
      rule: template
      text: "${note} (sent by Taktus for the team)"
      values:
        note: { $from: draft }

takeover:
  sequence: >
    Every Monday morning, a member of the team writes the note and signs it.
  steps:
    draft:
      system: the team's chat
      do: write two sentences that open the week, without names or dates
      expertise: none
      credentials: []
      done: two sentences are written
    sign:
      system: the team's chat
      do: add "(sent by Taktus for the team)" after the two sentences
      expertise: none
      credentials: []
      done: the signed note is ready to send
```

The `draft` step names a **purpose**, `writing`, not a model. The instance's configuration
decides which model serves it (*Adding a model provider*).

## Checking and registering it

`taktusctl bundle check` holds the bundle to the rules registration holds it to, without an
instance:

```bash
uv run taktusctl bundle check weekly-note.yaml
```

On an instance, `taktusctl submit --process weekly-note.yaml --identity <identity> --tenant
<tenant>` registers it and starts a run. At level 2 the run then waits for a person to confirm
the first step. The administration guide's page *Installing from nothing*, section 7, shows the
whole sequence.
