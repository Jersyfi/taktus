---
id: UC-8.3
title: Running on the organisation's own hardware
component: catalog
epic: E8
serves: [P3, P11]
state: specified
version: 0.4.0
tests: []
adrs: {ADR-0025: cba7351885b6, ADR-0031: e81473d81850}
supersedes: null
---

# UC-8.3 — Running on the organisation's own hardware

## 1. What must be achieved

Taktus runs self-hosted, including entirely locally with no dependence on an outside model
provider. Local inference is not a special case: for individuals and small organisations it is the
path Taktus aims at by default, and as local hardware grows stronger, running without an outside
provider becomes the default and an outside model a deliberate addition.

## 2. How it is verified

- An installation whose models are reachable only on the organisation's own hardware runs every
  example process whose steps such a model, or another method, can serve. A test runs the example
  processes against a local model endpoint with the instance's route to outside model providers
  closed.
- In the configuration offered to an individual or a small organisation, every purpose is bound to
  a local model by default. An outside provider is an explicit setting, with its location declared
  (UC-11.1).
- No capability of Taktus is available only through an outside provider. Finding one is a finding
  against principle 3.

## 3. Where the boundary lies

**Not equal quality.** A local model may do worse; the requirement is that it can be chosen and
runs. **Not the hardware.** Taktus uses what is there and reports what it can do (ADR-0031); it does
not supply it. **Not the installation itself.** Running Taktus on a home server, in a company or in
a regulated environment is definition `UC-10.1`.

## 4. What it rests on

The model contract (UC-8.1); residency and the location of every adapter (UC-11.1); where an instance
may run (ADR-0025); what an instance observes of its platform (ADR-0031). Definition `UC-8.3`. The
version is `0.4.0`, with the model hub for in-house models.
