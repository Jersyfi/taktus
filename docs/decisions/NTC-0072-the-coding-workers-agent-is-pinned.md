# NTC-0072 — The coding worker's agent is pinned

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#134](https://github.com/Jersyfi/taktus/pull/134)

## 1. What was decided

The coding worker's image and the live test install the agent at one exact version. The version
is written in one file, `workers/claudecode/agent-version`. Today it names 2.1.295.

- **Old:** the image installed whatever the agent's registry called `latest` when it was built.
  Two builds of one release tag could carry different agents, and the tag did not say which. The
  live job installed `latest` too, on purpose, so that it would notice a change of the agent.
- **New:** the image reads the file and installs that version; a file that names anything but
  an exact version fails the build. The release build passes no build argument that could
  override it. The live job installs the version from the same file, so that it proves what a
  release ships. It still notices a change: when the registry has a newer release than the pin,
  the job says so on its page, and installs nothing else.
- **A new version is taken by a pull request** that changes the file. It is proven by the live
  test, dispatched on `main` or at its monthly run, before a release is tagged
  (`workers/claudecode/README.md`, *The agent's version*).

## 2. The evidence

- Issue #116 asks for the pin and names its verification: the version written in the
  repository, a test that fails on `latest`, and the README saying which version a release
  carries and how it is raised.
- DEC-0038: the first live run found that the real agent's stream differed from the stand-in,
  and the worker undercounted tokens. An agent that changes between two builds can change the
  worker's accounting with it.
- 2.1.295 is the version the last passing live run installed. That run, 37849702313 of the
  workflow `live`, started on 2026-10-08 at 21:52 UTC. The registry had published 2.1.295 at
  18:22 UTC that day, and it was `latest` then and on 2026-10-09. The pin therefore raises
  nothing; issue #116 leaves raising the version to a change of its own.
- `tests/governance/test_image_workflow.py` fails when the file names `latest`, `^2.1.295` or
  `2.1`, when the Dockerfile declares a build argument or installs anything but the file's
  version, when the release build passes a build argument, and when the live job installs
  anything else.

## 3. What was considered

- **A build argument with the version as its default, passed by the release workflow.** Not
  taken: the live job would need the value from somewhere else, and an argument can be
  overridden by any build. With the file read inside the build, a local build, a test build and
  a release build install the same agent, and nothing passes a value.
- **The live job keeps installing `latest`.** Not taken: it would then prove a version no
  release carries, and pass while the shipped image fails, or fail while it works. A notice of
  the newer release keeps what the old behaviour was for.
- **A dispatch input to the live workflow naming a candidate version.** Not taken: the live
  workflow runs on `main` only (DEC-0048), so the candidate is the merged file anyway, and an
  input would add a second place a version comes from.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #116.
The worker contract, the worker's options and its outputs are unchanged; only which agent the
image and the live job install is fixed. No limit or level moves.
