# ADR-0089 — A launched worker reaches the hosts its own service needs, as the operator configures them

**Status:** accepted · builds issue #269 (roadmap `0.2.0`); extends ADR-0078 by one setting per
worker, and narrows what DEC-0008's `frame.allowed_hosts` says about a unit's reach

## Context
A step's frame names the hosts a worker may reach, and nothing else (DEC-0008). Two execution
kinds enforce it at the network. The `container` kind runs a unit behind an egress proxy of
its own. The `cluster` kind does the same with a proxy Job (`deploy/k8s/README.md` §6). The
launched worker (`adapters/driven/workers/launched.py`) handed the execution port exactly the
frame's hosts.

A coding worker drives an agent, and the agent calls its provider's API to work at all. That
host is in no step's frame. P-03's `implement` step names one host, the repository's. On the
workstation, where the `process` kind enforces nothing, this never showed (DEC-0022). On the
installed instance, on 2026-10-12, the coding worker could reach the repository and not its own
provider, and so could do nothing. The worker conformance suite failed the same way: its unit
was started with no host at all.

The host could be put into the frame. Then every bundle with a coding step would name the
provider of whichever agent the operator happened to configure. A bundle names capabilities,
never products (ADR-0003), and the same bundle runs on either coding worker (ADR-0078). The
provider is the worker's, not the step's.

## Decision

### 1. The operator names the hosts a worker's own service needs, as configuration
`TAKTUS_EXECUTION_SERVICE_HOSTS` is a comma-separated list of hosts. A named worker sets its own
as `TAKTUS_WORKER_<NAME>_EXECUTION_SERVICE_HOSTS` and otherwise reads the instance's, as every
execution setting is read (ADR-0078 §2). Each entry is validated as a frame's host is: a
lowercase host name or an IPv4 address, optionally with a port, no wildcard, none twice. A wrong
entry stops the start with one sentence naming the variable. Unset or empty, there is none.
The chart renders it from `execution.defaults.serviceHosts` and from `serviceHosts` of an entry
of `execution.workers[]`, where an empty list is that worker's own *none*.

No bundle names them. A process version carries no host its worker's provider needs, and
switching a coding worker from one agent to another changes configuration, not a process.

### 2. The execution unit carries them; the launched worker adds them to an assignment's job
`ExecutionUnit.service_hosts` carries the list from the configuration to the launched worker.
For an assignment, the job's `allowed_hosts` is the frame's hosts followed by the service hosts,
each once (`ports/execution.py: reach`). The execution adapters are unchanged: they enforce the
job's list, whatever it was made of.

**A probe gets none.** The unit started to answer `capabilities` or an estimate has no
credential and no host, as before. A probe that cannot call its provider is the point: nothing
runs before admission has said yes (ADR-0005).

**The conformance suite's unit gets the suite's hosts and the service hosts.** The suite's task
reaches the hosts `conformance.worker.hosts` names, as a frame does, so the unit started for the
suite gets those and the service hosts. Without them the suite tested a worker that could not
work. W-13, which narrows the frame by one host, still tests the worker's own refusal: the
network would let the request through, and the worker must refuse it.

### 3. The frame handed to the worker stays the step's
The worker receives the assignment's frame unchanged. It holds every tool call against that
frame and refuses a call to a host outside it (W-13), a service host included. The frame keeps
meaning what the step may reach. The service hosts are the operator's declared infrastructure
for the worker itself, reachable by the agent's own connection and granted to no step.

### 4. A record names what was allowed
The configuration a conformance pass or a removal verdict names (`Pools.configuration`,
ADR-0044 §2, ADR-0030 §5) states a launched worker's service hosts in a field `hosts`. A worker
that names none has no such field, so that a configuration recorded before this decision still
compares equal to the same configuration now. A worker whose service hosts change is another
configuration, and its standing is measured again (ADR-0044 §4). A worker reached by endpoint
records none: no unit is started for it, and nothing it names would be enforced.

### 5. Where the reach is not enforced, service hosts are refused like any host
With `execution.egress.enforce: false` the cluster adapter refuses a job that names hosts
(`deploy/k8s/README.md` §6). Service hosts are hosts. A worker that names them cannot run on
such a cluster. The alternative, starting the job with a list nothing enforces, is the one
thing §6 says must never happen.

## Alternatives
- **Name the provider's host in the step's frame.** It works today. Every bundle with a coding
  step would then name a product's host, and a bundle written for one agent would fail on the
  other. The frame would also stop meaning what the step may reach.
- **Let the worker declare its hosts in its capabilities.** The worker knows its agent's
  provider. But a declaration is the worker's word, read from a unit Taktus started; the reach
  a unit gets would then be set by the unit itself. The operator, who chose the provider and
  holds its credential, is the one who should grant it.
- **Allow the provider's host for every unit, as an instance-wide exception of the proxy.**
  Fewer settings. Every worker would reach every provider, a script worker included, which is
  more than least privilege allows (DEC-0008).
- **Add the service hosts to the frame the worker receives as well.** The worker would then
  approve tool calls to its provider's host, for instance a fetch through its own web tool.
  Keeping the frame the step's keeps that call refused.

## Consequences
- `ports/execution.py`: `ExecutionUnit.service_hosts` and `reach`. `workers/launched.py` uses
  `reach` for an assignment and nothing for a probe; `composition/conformance.py` for the
  suite's unit.
- `composition/settings.py`: the setting, its validation and its line in the startup log.
  `composition/execution.py`: `service_hosts` by adapter identifier, which the worker pool keeps
  and `Pools.configuration` records. The catalog's `Configuration` gains the optional `hosts`.
- The chart: `execution.defaults.serviceHosts` and `workers[].serviceHosts`, rendered into the
  ConfigMap. `deploy/k8s/README.md` §2, §6 and §7, `.env.example`,
  `docs/architecture/contracts.md` §2.4, `docs/architecture/project-structure.md`, the two coding
  workers' READMEs.
- P-03 becomes version 6: its statement of autonomy says the unit reaches the frame's hosts and
  the service hosts the operator configures, not the frame's alone.
- No contract changes. The worker contract's frame, W-13 and every check of the suite are as
  they were. No migration: the new field of `Configuration` is optional.

## Where this promise ends
A unit reaches its service hosts by name, through the proxy, on the proxy's allowed ports and
to no excluded address range; a provider on another port needs that port in
`execution.egress.ports` too. The proxy sees the name in a `CONNECT`, not the traffic: whatever
the agent sends to its provider is not inspected, and a provider host lets the agent send it
anything the unit holds, the workspace included. That is the agent's nature and the reason the
operator names the host and no step can. The worker's refusal of a tool call outside the frame
is the worker's own (W-13); an agent that opens a connection to its provider for its own
purposes is not a tool call, and the frame does not govern it. A service host is granted for
the whole of an assignment, not per call. On the `process` and `endpoint` kinds nothing is
enforced, as before (DEC-0022): the setting changes nothing there, and an endpoint worker
records none. The configuration a record names states the hosts as configured, not the
addresses they resolved to.
