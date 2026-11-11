Work you asked for runs as a **run**: one execution of a process, from its first step to its
last. Every run has an identifier that begins with `run_`. You follow it and stop it by writing
to Taktus where you asked for it.

## Where the answer comes

A run started by your message answers in the same thread. It says once that the run finished,
that it needs a person, or that it waits for your answer. The run's page in the web app shows
every step as it happens.

## Three things you can write

| You write | Taktus does |
|---|---|
| `status`, or `what are you working on?` | lists every run you may see that has not ended: its process, its current step, its state, since when, and what it waits for |
| `pause <run>` | halts the run before its next step; it can be resumed there later |
| `cancel <run>` | halts the run before its next step; it never resumes |

Taktus answers at once that it received the request. When the run has reached its next step, it
says in the same thread that the pause or the cancellation took effect. The step that runs
finishes first, so nothing it did is lost.

The answer to `status` is read from the **ledger**, Taktus's record of everything that happened.
It therefore says what the ledger says, and nothing else.

## Who may pause or cancel a run

You may pause or cancel a run that acts on your behalf. The owner of the organisation may pause
or cancel any run. Anyone else needs a role that holds the right `run.steer`. A refusal names
the right that was missing.

A paused run is not resumed from the chat. The people who administer Taktus resume it.
