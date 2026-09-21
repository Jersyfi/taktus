# ADR-0007 — Worker contract over HTTP and SSE

**Status:** accepted

## Context
The worker layer is the most volatile part of the system: coding agents appear and disappear within
months. The contract only lives if third parties can implement it without effort.

## Decision
HTTP for assignments and control, Server-Sent Events for the event stream, JSON Schema as the
definition. A worker must be buildable without knowing the core's language — as a script, as a small
service, as a shell wrapper around a foreign CLI.

## Alternatives
- **gRPC** — more efficient, type-safe, and a barrier. Efficiency is not the bottleneck here;
  adapter variety is. It can be added as a second binding in v2.
- **In-process plugins** — fastest path, but a worker crash takes the control plane with it.
- **Adopting ACP directly** — watched. While it addresses agent-to-client rather than
  orchestrator-to-execution-unit, it lacks estimation, step boundaries and consumption reporting.

## Consequences
- Two proof cases are mandatory from `0.1.0` and part of the conformance suite: a shell script with
  no AI at all, and a training run that occupies a GPU for hours and returns a model artifact. A
  contract only one of them can satisfy is built around one specific agent.
- A second real worker exists before any feature builds on worker behaviour.

## Where this promise ends

A worker buildable in any language is a promise about the transport and the schema, not about
the effort of a *good* worker: estimating demand before starting (W-08) and signalling step
boundaries (W-09) are the two obligations a wrapped foreign CLI struggles with, and a wrapper
that cannot estimate gets a rejected assignment, not a pass. The conformance suite proves W-01
to W-11 and W-13 against a live worker; W-12, the removal test, is proven by the process under
`blueprints/self-operation/`, per installation, not by the suite (DEC-0005). Two proof cases
are promised; the second, `mlbench`, does not exist yet.
