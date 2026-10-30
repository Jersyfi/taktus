# ADR-0158 — Every connector is an image of its own

**Status:** accepted · extends DEC-0011 (no worker code in the control plane image), ADR-0009
(the connector contract) and ADR-0118 (the release list) · issue #339, UC-14.4

## Context

A connector is an MCP server that reaches one product outside Taktus with a credential the
requesting identity owns. The control plane reaches it over MCP and nothing else
(`contracts/connector/v1`). Until this decision every connector lived in the control plane's
package, `src/taktus/adapters/driven/connectors/`. The control plane image therefore carried
all of them. The chart and the one-server install started each connector from that image, with
its module as the command.

Three facts made that wrong.

- **A connector is a separate deployable.** DEC-0011 holds this for workers, and the reason is
  the same: code that reaches outside is present in the tier that decides, even where it is not
  started. A compromised control plane would find a client for every product ready to hand.
- **Adding a connector changed the core image.** A new connector, or a fix to one, was a new
  control plane image. The issue asks the opposite: adding a connector never changes the core.
- **The catalogue of `0.6.0` lists connectors by capability and maturity** (docs/roadmap.md).
  It cannot list what ships as an image when nothing ships as one.

## Decision

### 1. The connectors move to `connectors/`, a package of their own

Every connector served as an MCP server moves to `connectors/taktus_connectors/<name>/`, beside
`workers/`. Its shared serving library moves with it, as `connectors/taktus_connectors/serving.py`.
The import name is `taktus_connectors`.

The move is a rename. Each connector keeps its files, its README, its scenario and its faults.

### 2. Neither side imports the other

A connector imports nothing from `taktus`. The control plane imports nothing from
`taktus_connectors`. `.importlinter` holds both directions as contracts, and
`tests/architecture` holds them on the source. The vendor connector bound four contract types
from the control plane's ports. It now binds them itself, held to the contract's examples by
its existing test.

### 3. What stays inside the control plane

Four things stay under `src/taktus/adapters/driven/connectors/`:

- `mcp/`, the client that reaches every connector. It is the port's adapter, not a connector.
- `pool.py`, the configured connectors resolved by capability.
- `loopback/`, which serves the instance to its own processes. What it reaches is the instance.
- `directory/`, which serves pages as files on the instance's own volume. What it reaches is that
  volume.

The last two run in the process that uses them. Serving them from another image would put a
second deployment on the control plane's state. `tests/architecture` fails when anything else
appears there.

### 4. One image per connector, one stage per image

`connectors/Dockerfile` has a stage per connector, built on a shared base. The base holds the
libraries and the serving library. A stage adds its own connector's directory and nothing else,
and its entry point is the connector's module.

The libraries come from the lock file. `pyproject.toml` names a dependency group `connectors`.
The build exports that group from `uv.lock` with its hashes and installs exactly that. A
connector's image runs the versions the tests ran. No other library of the control plane
reaches it.

The image is named `taktus-connector-<name>`, after the connector's directory. The release
workflow builds and pushes every stage with the release's version (`.github/workflows/images.yml`).

### 5. The chart and the one-server install start each connector from its image

The chart derives the image from the control plane's: `<image.repository>-connector-<name>` at
`image.tag`. `connectors.imagePrefix` replaces the prefix for an operator who pulls connectors
from elsewhere. The repository and chat connectors run from their images. An entry of
`connectors.others` names a shipped connector as `connector: <name>`, or brings an image of its
own.

`deploy/docker/connectors.py` writes a compose service that builds the connector's stage from
the checkout, `taktus-connector-<name>:local`, as `compose.yml` builds the control plane's image.

### 6. An installed instance upgrades without a change to its values

The chart's values and the operator's `connectors.json` named a connector by its module:
`taktus.adapters.driven.connectors.stripe`. That module is no longer in the control plane
image. An entry that names it is read as the connector it names. It runs from that connector's
image. A module that names no shipped connector is refused at render time, with what to write
instead.

No value of the chart is renamed, and none becomes required. The repository and chat connectors
change their image without a change to their values. The images for them must be in the
registry the control plane's image comes from. The release workflow puts them there.

### 7. The release list carries each connector's image

`composition/shipped.json` lists every connector with its image. A connector that runs inside
the control plane has none. `taktusctl conformance list` prints the configured adapters with
their maturity, as before. After them it prints, by capability, every connector the release
ships with its image.

## Alternatives

- **One image holding every connector, apart from the control plane's.** It would empty the
  control plane image. Adding a connector would still change the image of every other
  connector, and a compromised connector would find every other product's client beside it.
  Rejected.
- **One distribution per connector, each with its own project file.** It is the strictest
  separation. It would give twelve lock files that drift apart, or a workspace whose members
  the control plane's build must still see. The stage per connector gives the same image
  boundary from one lock file. Rejected.
- **A build argument naming the connector.** One stage would serve all. The release build
  passes no build argument, so that none can override a pin (`tests/governance`). A target is
  not an argument. Rejected.
- **Move the loopback and directory connectors too.** Both reach the instance itself. Serving
  them from another deployment would make a second writer of the control plane's volume.
  Rejected.

## Consequences

- `connectors/` holds the twelve connectors, `serving.py`, `Dockerfile` and `README.md`.
- `pyproject.toml` builds `src/taktus` and `connectors/taktus_connectors` into one wheel for
  development and the tests. The control plane image copies `src/`, never `connectors/`. A
  connector's image copies its part of `connectors/`, never `src/`.
- `tests/images.py` builds each connector's image by its stage. `tests/integration/test_control_plane_image.py`
  checks that the control plane image has no connector code. `tests/conformance/test_connector_v1_images.py`
  runs the suite against every connector from its image.
- `tools/lanes.py` claims `connectors/` for the lanes that test it, and `tools/checkdocs.py`
  asks a change there for its documentation.
- `composition/shipped.py` names the connectors' package as text and imports it only when the
  repository is there (`make generate`).

## Where this promise ends

- **The promise is the image boundary, not a sandbox.** A connector's image holds no control
  plane. What the connector reaches at run time is its network policy's and its credential's
  business, as before.
- **A connector's image tag is the release's.** A connector fixed between releases is a new
  release of all images. A connector released on its own schedule is not promised here.
- **Twelve connectors are proven from their images.** The suite runs against each one, faults
  excluded: the faults are proven against the same code as a process (`tests/conformance`).
- **The mail connector is proven with its fake beside it.** It refuses to send a password in
  clear to another machine, so it shares the network of the container its fake runs in.
- **A connector of a third party is an image of its own already.** Listing third-party
  connectors in a public catalogue is #348, not this decision.
- **A maturity belongs to a configuration** (ADR-0044). A shipped connector that no instance
  configured has a capability and an image, and no maturity.
- **The upgrade path reads the old module names.** It does not read a module of the operator's
  own. Such an entry was never supported: the control plane image held no operator code.
