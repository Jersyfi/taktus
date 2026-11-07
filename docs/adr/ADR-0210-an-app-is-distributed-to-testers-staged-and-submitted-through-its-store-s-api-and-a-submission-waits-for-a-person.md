# ADR-0210 — An app is distributed to testers, staged and submitted through its store's API, and a submission waits for a person

**Status:** accepted · extends ADR-0150 (connectors for the systems a business names), ADR-0158
(a connector is an image of its own) and ADR-0195 (release processes) · issue #438, UC-03 §4.8,
§8 "app stores: reviews, submission, beta, staged rollout"

## Context

UC-03 stage 3 releases a mobile app as well as a web service: a finished build goes to testers
and their feedback becomes issues (B-8.02), an approved release is submitted and its review
followed (B-8.03), and a published release is raised in stages by its crash rate and halted on a
rise (B-8.04). ADR-0195 left the stores out: each store's interface is one vendor's.

A mobile app is distributed through two stores, one per platform, and the two most widely used
publish an API for exactly these acts: App Store Connect for iOS and the Google Play Developer
API for Android (ADR-0150: the most widely used product for a capability). A business with an app
on both platforms needs both behind the same capability. The run resolves an action's connector
by the capability it declares, and the first that declares it wins: two connectors cannot serve
one capability side by side.

## Decision

### 1. One connector serves `stores.beta` and `stores.releases`, per call by platform

A connector under `connectors/taktus_connectors/appstores/` speaks both stores' APIs. Every
operation takes `platform`, `ios` or `android`, and the call goes to that platform's store:

| Operation | Effect | What it does |
|---|---|---|
| `stores.beta.builds` | read | the app's builds, newest first, with the store's own processing state |
| `stores.beta.distribute` | write, `marked` | a build added to a tester group, or released on a test track |
| `stores.beta.feedback` | read | testers' feedback — its comment, kind, build and time — never the tester; one store publishes none, and asks for it there are `invalid` |
| `stores.releases.read` | read | a version's state, its review mapped to `preparing`, `waiting`, `in_review`, `rejected`, `approved`, `live` or `other`, and its staged rollout |
| `stores.releases.raise` | write, `marked` | the staged rollout raised to a share of users; a store with its own schedule resumes it, and completes it at a share of 1 |
| `stores.releases.halt` | write, `marked` | the staged rollout halted or paused |
| `stores.releases.submit` | write, `marked` | a version submitted to the store's review, or released to production |

The credential is one document with a member per platform: an API key of the one store, which
signs a token per call, and a service account key of the other, which is exchanged for an access
token per call. Either member may be absent.

### 2. The mark is the key where the store has a field for it, the state where it has none

A release one store makes carries a `name`, shown only in its console: the key's mark goes
there, and a repeat finds it. The other store's writes, and the raise and the halt on both,
have no field for a key: the state a write leaves is its own mark, weaker than a key, and stated
so, as a scale's number is (ADR-0195 §1). The conformance suite judges the keyed write; the
connector's tests prove every repeat.

### 3. A submission is a person's act at every level

Submitting a version is the technical lead's (UC-03 §4.8). B-8.03 submits only a version the store
still has in preparation, and the step carries `ask` (ADR-0088): a decision request at every
level, with the version and its state. B-8.04's halt is the process's own, by rule, as the
cluster's is (ADR-0023); resuming after a halt is a new run started by a person.

## Alternatives

- **One connector per store.** Each would declare the same capability; the second would never
  be resolved. A capability per store would put a product's name into the processes.
- **A deployment service that wraps both stores.** One more product between the business and its
  stores, with an account and a price of its own; the stores' APIs are under it anyway.
- **Feedback from a crash reporter instead of the store.** It reports crashes, not testers'
  comments; the error tracker already serves crashes (`errors.issues`).

## Consequences

- A connector `appstores`, its fake under `tests/fakes/app_stores_service.py`, its scenario and
  its image, in the shipped list and the chart's list; `STORES_KEY` in `CREDENTIALS.md`.
- `blueprints/software-operations/processes/` gains B-8.02, B-8.03 and B-8.04's store version.
  A tenant registers the version of b-8-04 that fits its release; a stage counts either.

## Where this promise ends

- **Two stores.** Another store needs its own connector, and a tenant that uses it with these two
  needs a connector that speaks all three.
- **One store publishes no review state and no tester feedback through its API.** On its
  platform B-8.03 ends with the submission and B-8.02 files no feedback; a person follows both in
  its console.
- **One store takes no share for a staged rollout.** It follows its own seven-day schedule; a
  raise resumes it and cannot set a share, and the process's stages mean a day each, not a share.
- **A state is a weaker mark than a key.** A repeat after somebody else made the same state —
  submitted the same version, set the same share — reports replayed.
- **Metadata, screenshots and prices are not written.** The store texts are drafted by B-8.01
  for a person to enter; the processes change nothing a store shows its users but the release.
- **The crash rate is the tenant's query.** B-8.04 reads what its query answers through
  `metrics.series`; a query that does not measure the release alone measures something else.
