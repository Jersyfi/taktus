A **worker** carries out the task of a `worker` step: it runs a script, a coding agent, a
training job. It is an HTTP service: it answers the endpoints below and reports progress as
Server-Sent Events, a stream of messages over one HTTP response. It can be written in any
language, and it imports nothing of Taktus.

A worker states what it can do as **capabilities**, such as `shell.script`. A step names the
capabilities it requires, and Taktus hands it to a worker that offers all of them. The worker
does the task inside the frame it is given: those capabilities, the hosts it may reach, and what
is left of the run's budget. It decides nothing beyond the task.

`workers/script/worker.py` is the smallest worker of this repository: a shell wrapper with no AI,
in one file of the standard library. The other workers under `workers/` show agents and training
jobs behind the same contract.

An instance reaches a worker by its address, `TAKTUS_WORKER`, or several by name through
`TAKTUS_WORKERS` (`.env.example` describes both). A worker in a network that admits no inbound
connection can connect to the instance instead.

The rest of this page is the contract's own text: its endpoints, and how the conformance suite
checks a worker.
