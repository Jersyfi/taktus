# ADR-0108 — A rehearsal can replay a recorded run, step by step

**Status:** accepted · extends ADR-0030 · rings 1 and 3 of ADR-0096 §1, phase 3 of §6 · issue #393

## Context

ADR-0096 places a rehearsal of the self-development bundles in ring 3: every commit on `main` proves that P-01, P-02, P-03 and S-07 still run. A change that breaks a bundle, or the engine's handling of one, should turn `main` red after the merge, not on the instance a day later.

A rehearsal as ADR-0030 defines it cannot do that in CI. It answers only an *outward* connector operation from a recording. A read is a real read. A model step calls a model. A worker step hands its task to a coding agent. In CI each of these would read the repository host, spend money on a model and run an agent. Each needs a credential, and a test that needs a credential never runs on a commit of this public repository (CLAUDE.md §9, DEC-0048).

ADR-0030's recording is also chosen by operation and adapter: the most recent real call of that operation. P-03 calls `repository.labels.set` twice and `repository.comments.create` twice. A recording chosen by operation would answer both steps with the same answer.

## Decision

### 1. A replay answers every step that would leave the engine, by step

A *replay* is a rehearsal whose every step that would leave the engine is answered by the recorded result of the same step, in a real run of the same process. A step leaves the engine when it calls a connector, waits on a connector's state, asks a model, or hands a task to a worker. Rules, admission, the step boundaries, conditions and the engine's handling of every step run as in any run.

The engine is given the replay through a port (`components/run/ports/replay.py`). The port offers the three pools the engine resolves from in any run: workers, connectors and models. An engine given a replay resolves every rehearsal it executes from the replay, and never from its configured pools. So an outward operation of such a run goes to the replay, which acts on nothing. It finishes `rehearsed` and writes no egress entry, as in ADR-0030 §2. Every ledger entry of the run carries `rehearsal: true`. Between the step and the recorded answer the engine's own code runs unchanged: the estimate, admission, the hand-over to a worker, its stream of events, the artifacts and their digests.

A replay asks every step boundary as a run does: the anchors (ADR-0042), a step's own `ask` (ADR-0088), and the autonomy level (ADR-0039). This is where it departs from ADR-0030, whose rehearsal asks none of them (NTC-0079). A replay is not asked an adapter's maturity: its adapter is the recording, which has no maturity. A replay decides nothing for a person. A step that waits for a person halts there, as in any run.

### 2. A step must send what the recorded step sent

Each step's request is compared with what the recorded step sent. The comparison is strict: a step whose request differs in any part fails. The reason names the step and the parts that differ. A step whose recorded answer is missing fails too, and the reason says so.

- A connector call and a wait carry their step. Each is matched by its step id. Then its operation must equal the recorded one, and its input must have the same digest.
- A model call and a worker's assignment carry no step. Each is matched by the digest of its request among the recorded steps of its kind. A request that no recorded step sent fails. The reason names the recorded steps of that kind, and where each one's request differs.

The request of a connector call and of a wait is the operation and its input. The request of a model call is the system text, the prompt and the output limit. The request of a worker step is its task: the goal, the acceptance criteria, the inputs and the commands before and after the work. The workspace, the frame and the limits are not part of it. They belong to the engine and the configuration, not to what the step asks for.

The comparison is strict because loose matching on the operation and the step alone would let a bundle send something else unnoticed. A changed comment body, a changed prompt or a changed task would then be answered with the answer to the old one.

### 3. The replayed run must come where the recorded run came

After the replay, each step's state is compared with the state it reached in the recorded run. The run's end is compared too: its state and its cause. Each difference is one line that names its step. A replay *holds* when there is none.

Two things are not a difference. First, a step that waited for a person in the recorded run, and waits for one in the replay, has reached its boundary as recorded. Second, the steps that depend on such a step are not reached in the replay, and are not compared. Everything else is a difference:

- a step the recording does not know;
- a recorded step the bundle no longer has;
- a state that differs;
- a run that ended otherwise.

### 4. The replay runs as the recorded run ran

The replay starts under the recorded run's identifier, with its inputs, the budget it ended with, its margin, and the price table and the margin for a worker without a calibration history that the instance used. A run's identifier is unique only within a tenant (ADR-0104), so each replay runs in a tenant made for it. A step that derives something from the run then derives what the recorded step derived. An idempotency key (ADR-0099) and a template that names the run are two examples. A wait does not wait. The replay's clock moves forward by what a step would have slept, so a wait polls as often as it would and takes no time. A wait that ended as expected sees, at its first poll, the first value it expected. A wait keeps no result (ADR-0018), so the value the recorded wait saw is not known.

### 5. A recording is data, content-free where the ledger is

A recording is a directory (`adapters/driven/replay/recording.py`): `recording.json`, the result of each connector call and model call under `results/`, and the artifacts of each worker step under `artifacts/`. A replay reads nothing else. A recording is never code.

- What a step *sent* is recorded the way the ledger records content: as a digest. The recording holds the digest of the request and a digest per part of it, never the request itself. The parts are its top-level fields and the fields of each top-level object. That is enough to name what differs without anyone having kept what was sent.
- What a step *received* is kept as the run kept it: the result documents and the artifact bytes the steps after it read. That content is what the repository host, the model and the worker answered.
- No identity of a person is recorded. No reason in words is recorded. No secret value is recorded.

### 6. The export reconstructs, and refuses what it must

`tools/record_rehearsal.py` writes a recording from one run in an instance's database. It reads the database where every Taktus command reads it: from `TAKTUS_DATABASE_URL_FILE`. A URL holds a password, so it is never an argument. It reads the object store from `$TAKTUS_STATE_DIR/objects`. It writes nothing but the directory and changes nothing in the database. It reconstructs what each step sent from what the run kept — the step's work, the run's inputs, the results of the steps before it — through the same domain functions the engine resolves a step with. It derives the declaration of each operation from what the run shows. The effect is taken from the result. An outward operation is declared as one that recognises a repeat: a replay never repeats one. The most one call consumes is the step's estimate divided by the calls the estimate was for. The export refuses five things, and then writes nothing:

- a run that is a rehearsal;
- a run that has not ended;
- an output directory that is not empty;
- an `ml` step, which it does not record yet;
- a recording that holds the value of a secret the environment points at, the database URL among them.

The tool runs inside the instance's runner image, with the `taktus` package and Python and nothing else. That image may predate the replay's module. So the tool keeps its own copy of the format and of the request digests, and a test holds that copy to the replay's.

### 7. The replay is a lane of CI

`make rehearse` replays P-01, P-02, P-03 and S-07, each with its bundle as it stands under `blueprints/` and its recording under `tests/rehearsal/recordings/<process id>/`. It runs against a PostgreSQL database. It is a lane of CI like the others (ADR-0096 §3): `tools/lanes.py` selects it for a pull request that touches a bundle, a recording, the export tool, a migration or any module under `src/`. Every module under `src/` counts because the replay reaches the core through the composition root, whose import graph holds nearly all of it; a test holds the lane to every module the replay imports. A push to `main` runs it unfiltered, and like every run on `main` it is never cancelled. `make verify` runs it wherever CI would. It is handed no secret: it needs none, so it may run on a pull request (CLAUDE.md §9 keeps only a credentialed test off one). A change that alters what a step sends is therefore red before it merges, and does not turn `main` red for every pull request behind it (ADR-0096 §5). The suite includes deliberate breaks, and each must turn the replay red, naming its step. A bundle that sends another body is one. A recorded answer that no longer leads where it led is another. A missing answer is the third. `make test` leaves the directory out; the lane runs it.

### 8. A change that alters what a step sends records that process again

A pull request whose change alters what a step sends — an operation, its input, a prompt, a task, a step added or removed — records that process again in the same pull request. It takes the local recording from the repository's fakes (`TAKTUS_RECORD_LOCAL=<process id>`, `tests/integration/test_rehearsal_recordings.py`), which writes that process's directory alone. This holds whether the recording it replaces was local or from the instance. A recording from the instance replaced so is local again (`"taken": "local"`), and stays local until the new version has run on the instance and its run is recorded there. Nothing else is accepted: the replay is never weakened to let a changed request pass.

The first recordings are local: runs of the four bundles against the repository's fakes, on a developer's machine. Each says so in its own `recording.json` (`"taken": "local"`) and in the directory's README. A recording taken on the instance replaces each of them.

## Alternatives

- **Replay at the adapters only, without touching the engine.** Pools of recorded adapters, and a run that is not a rehearsal. It would write egress entries for effects that never left the system. At level 3 it would also need maturity records for adapters that are only recordings. As a rehearsal of ADR-0030, its outward operations would go to the recording by operation, and P-03's two calls of one operation would get one answer.
- **A field `replay` on the run.** It needs a migration, and a replay is a property of the engine's wiring, not of the run. An engine that is given no replay is the engine of ADR-0030, unchanged.
- **Match by operation and step only.** A bundle that sends another body would be answered with the old answer, and the change would reach `main` unseen. The issue asks for exactly that change to turn `main` red.
- **Keep the requests in the recording.** A difference could then be shown in full. The recording would then keep content the ledger keeps only as a digest. The digests per part name what differs, and the content of what was sent is in the bundle and in the results the recording keeps.
- **Fakes instead of recordings.** ADR-0030 rejected them: a fake rehearses the fake. The repository's fakes make the first recordings, until the instance's replace them.

## Consequences

- The run component gains the port `Replay`. The engine gains a replay and resolves every rehearsal from it when it has one. A pure comparison (`domain/service/replay.py`) states how a replayed run differs from its recording.
- A driven adapter `adapters/driven/replay` holds the recording format, the request digests, and a connector, a model and a worker that answer from a recording. The composition root `composition/replay.py` wires a replay against the stores it is given.
- No migration.
- A change that alters what a step sends is red in its own pull request until it records that process again (§8). That is the purpose. A process whose recording came from the instance falls back to a local one with that change, until the instance records the new version.
- Rings 1 and 3 of ADR-0096 run the replay: a pull request where it selects the lane, `main` always. Phase 3 of its §6 is done for this part once the recordings come from the instance.

## Where this promise ends

A replay proves that the bundles and the engine still come where a recorded run came, with the answers that run received. It does not prove that the repository host, the model or the worker still answer so. That proof is the monthly live tests' and a release candidate's run on the instance (ADR-0096). A recording is as old as the run it was taken from, and a local recording proves only the replay and the export, not the instance. A pull request that changes what a step sends records that process again from the repository's fakes, so from then on that process is proven against the fakes and not against the instance, until the instance runs the new version and its run is recorded. The lane selects by path. A change that alters what a step sends through a file the lane does not claim is found on `main`, not in its pull request. The export reconstructs what a step sent with the domain functions of the image it runs in. A step whose work the engine resolves in a way those functions do not capture is recorded as sending something else, and its replay fails. The declaration of an operation is derived from what the run shows. Its idempotency and its demand are not the connector's own words. An operation the run never estimated has no demand, and its step is refused in the replay as it was in the run. A wait is answered with the first value it expected, because a wait keeps no result. A replay does not decide for a person. The steps after a person's boundary are not replayed. A recorded run that went on after a decision is compared only up to that boundary. Admission is held as in a new tenant, without a calibration history. A step the instance admitted with its history may be refused in the replay, and that is reported as a difference, not hidden. A model call and a worker step are matched by their request. Two steps that send the same request get the answer of the first. An `ml` step is not recorded. The secret check of the export finds the values the environment points at. It does not find a secret that came from elsewhere. The repository's secret scan is the second check.
