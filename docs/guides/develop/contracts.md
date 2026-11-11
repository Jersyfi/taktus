A **contract** is the published description of how Taktus and something outside it talk: a JSON
Schema, and for the worker also an OpenAPI document of its endpoints. Each lives in its own
versioned directory, `contracts/<family>/v<N>/`:

| Directory | Describes |
|---|---|
| `contracts/worker/v1` | a worker |
| `contracts/connector/v1` | a connector |
| `contracts/model/v1` | a model's declaration, its usage per call, and the price tables |
| `contracts/shared/v1` | the concepts the others share, such as a step |
| `contracts/events/v1` | the events of other tools that can start a process |
| `contracts/changes/v1` | the changes of a run, a step or a decision request, as a reader receives them |
| `contracts/catalogue/v1` | the catalogue of signed adapters and bundles |

`contracts/process/v1` is reserved for the process bundle. Until it is filled, the bundle's shape
is the one *Writing a process bundle* describes.

The worker, connector and model contracts each come with a conformance suite:
`uv run taktusctl conformance run --contract <family>/v1`. A pass is evidence for a person; an
instance measures its adapters itself.

The rules below say what may change in a published contract, and how a change is announced.
