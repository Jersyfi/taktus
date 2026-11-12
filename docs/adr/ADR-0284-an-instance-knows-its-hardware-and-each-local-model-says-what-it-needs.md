# ADR-0284 — An instance knows its hardware, and each local model says what it needs

**Status:** accepted · extends ADR-0031 (Taktus watches the platform it runs on) · applies
ADR-0025 and ADR-0020 · serves UC-10.1

## Context

UC-10.1 asks that Taktus runs anywhere: on a home server, in a cluster, cut off from outside
networks. It asks that the resources an instance has are detected and shown, and that for each
local model it is shown which hardware it needs and whether the instance has it. It asks that one
release runs in every variant, with configuration as the only difference.

ADR-0031 gave the core a platform port. That port says what is *free*: idle cores, available
memory, free storage. It says nothing about what the machine *is*. It does not know the processor
architecture, and it does not know whether a graphics card or another accelerator is attached.
`taktusctl load measure` states the machine it measured on, but only processors and memory, and
only beside a measurement.

A model on own hardware is configured like any other model (`TAKTUS_MODEL_LOCATION=own`,
`TAKTUS_MODEL_BILLING=per_hardware_time`). Nothing says what that model needs. An operator who
moves an instance from a machine with a graphics card to one without learns it from the first
step that fails.

## Decision

1. **A hardware port.** `taktus.ports.hardware.Hardware` answers one question: what the machine
   under this instance has. The answer, `HardwareInventory`, holds the processors (count and
   architecture), the memory in bytes, and the accelerators. Each figure names its source. A
   figure the adapter cannot read is `None` with the reason, never a guess, as ADR-0031 requires
   of the platform port.
2. **An accelerator is described by kind, never by product.** Two kinds exist:
   - `graphics`: a device the kernel lists as a display or 3D controller;
   - `accelerator`: a device of the kernel's class for compute accelerators.

   A device carries its vendor as the identifier the device reports (a PCI vendor number), its
   memory where the device states it, and the place it was found. No vendor's name is in the
   core. A class of processor that does not exist yet appears in the second kind the day its
   driver registers it with the kernel, and needs no change here.
3. **The host adapter reads files of the kernel's, and runs nothing.** It is
   `adapters/driven/platform/hardware.py`, standard library only, like the platform adapter.
   Graphics devices come from `/sys/class/drm/card*/device`. Accelerators come from
   `/sys/class/accel/accel*/device`. On a platform without `/sys` (macOS), the processors and
   the memory are read from the system configuration. The accelerators there are not observed,
   and the inventory says so with the reason.
4. **A model declares what it needs.** `TAKTUS_MODEL_NEEDS` (per member,
   `TAKTUS_MODELS_<MEMBER>_NEEDS`) is a list of `key=value` pairs: `processors=N`,
   `memory=<size>`, `accelerator=graphics|accelerator|any`, `accelerator_memory=<size>`. Sizes
   take `MiB`, `GiB` or `TiB`. A declaration is configuration and is shown with every other
   setting. A model without a declaration needs nothing that anybody said.
5. **The fit is a rule.** Governance compares each need with the inventory
   (`governance/domain/service/hardware.py`). Each need is `met`, `missing` or `unknown`, with
   the figure wanted and the figure found. A model at location `own` is local. It *fits* when
   every need is met, it is *short* when one is missing, and it is *unknown* when one cannot be
   checked. A model whose location is not `own` runs on someone else's hardware, and the report
   says so and checks nothing.
6. **`taktusctl hardware` shows it.** One line per figure of the inventory, then one block per
   configured model with its needs and their fit. `--json` prints the same as one document.
   Exit code 1 when a local model is short, so that an install script can stop on it. It needs
   no state and no database, and it changes nothing.
7. **One release, two variants, no route outside.** The same control plane image runs the same
   shipped process unchanged in two variants that differ in configuration only. One variant has
   no network at all and keeps its state in files. The other has a database on a network without
   a route outside. Both execute the same steps
   (`tests/integration/test_runs_anywhere.py`). The test needs Docker and runs in the lanes that
   have it, never in `make check`.
8. **No service of its maker.** With nothing configured, no setting of an instance names a host
   outside the machine. No address in the shipped code names the maker's domain except the
   namespace of the contracts' schemas, which is an identifier and never fetched
   (`tests/architecture/test_no_service_of_its_maker.py`).

## Alternatives

- **Run the vendors' tools (`nvidia-smi`, `rocm-smi`, `system_profiler`).** They report more:
  utilisation and model names. Each is one vendor's program, installed or not. Calling one would
  put a product in a code path, and its absence would read as "no accelerator". The kernel's
  device classes are the same on every Linux and name no vendor. An adapter per vendor tool can
  be added behind the same port when a measurement needs more than the kernel says.
- **Detect what a model needs from its weights.** A model's size gives a lower bound on memory.
  It says nothing about the precision it is served in, nor about the server around it. The
  operator who installed the model knows. Asking the operator once is exact; guessing is not.
- **A flag per model, `gpu=true`.** Too coarse. It cannot say how much accelerator memory is
  needed, and it has no word for a dedicated accelerator.
- **Extend the platform port.** Free capacity changes every second, and the inventory changes
  when the machine changes. Two questions with two lifetimes are two ports.

## Consequences

- New: `ports/hardware.py`, `adapters/driven/platform/hardware.py`,
  `governance/domain/model/hardware.py`, `governance/domain/service/hardware.py`,
  `governance/application/service/report_hardware.py`, `composition/hardware.py`, and the
  command `taktusctl hardware`.
- `ModelSettings` carries `needs`. `TAKTUS_MODEL_NEEDS` is in `.env.example`.
- `tests/integration/test_runs_anywhere.py` runs in the integration lane with Docker.

## Where this promise ends

- **The inventory is of the machine the control plane runs on.** A model served by another
  machine of the organisation (`location: own`, but a different host) is compared with this
  machine, which may be wrong. The report says which machine it looked at. An inventory of the
  serving machine needs an adapter there, which does not exist.
- **On a cluster, the node under the pod is what is seen,** not the node a worker's unit is
  scheduled onto. A device the cluster hides from the pod is not seen.
- **On macOS no accelerator is detected.** Apple silicon's graphics and neural engine are not
  in a file the adapter reads. The inventory says "not observed" with the reason; it never says
  "none".
- **A need is only as true as its declaration.** A model declared to need less than it does
  will pass the check and fail when it runs. The check reads configuration; it does not load the
  model.
- **Detection is not use.** This ADR does not schedule a step onto an accelerator, and it does
  not pass a device into a container. A model server the operator runs uses the device itself.
- **Exercised here:** the two variants and the closed network on one machine with Docker, the
  hardware adapter against recorded kernel trees of a machine with a graphics card and one with
  an accelerator. **Not exercised:** a real graphics card or accelerator, a cluster (the chart
  has its own target, `make verify-kind`), and a local model answering while the network is
  closed (UC-8.3).
