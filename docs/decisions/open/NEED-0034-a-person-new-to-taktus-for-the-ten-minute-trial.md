# NEED-0034 — A person new to Taktus for the ten-minute trial

**Kind:** action
**Raised in:** [#623](https://github.com/Jersyfi/taktus/pull/623)
**Issue:** [#619](https://github.com/Jersyfi/taktus/issues/619)
**Needed by:** 2026-11-13
**Foreseeable since:** UC-10.4 and ADR-0136, which measure the path from the install to a first rehearsed process with a person who has not used Taktus

## 1. What is needed

One trial: a person who has never used Taktus, and who is not technical, installs it and makes a
first rehearsed process, while `make start` measures the time. A session cannot be that person,
and cannot find one. You arrange the trial and hand over what it measured.

## 2. Why

The roadmap's `0.5.0` is complete only when "a person new to Taktus reaches a first rehearsed
process in ten minutes" (DEC-0195, W4). UC-10.4 holds only on a time measured with such a
person. The path itself is built and measured without a person (`make verify-first-process`,
`docs/runs/first-process-in-ten-minutes.md`). Issue #405 stays open until the trial is reported.

## 3. By when

**2026-11-13**, so that `0.5.0` can close on it. Without it, #405 stays open and `0.5.0` is not
complete.

## 4. How to provide it

1. Find a person who has not used Taktus and is not technical. Give them a machine that meets
   the installation guide's section 2.1, with Docker running, and a checkout of the repository
   at the newest tag.
2. Give them only the installation guide, `docs/guides/administration/first-install.md`. Tell
   them to type `make start` and to follow what the screen says. Help with nothing.
3. Note, without their name, every place they stopped: what they looked for, and how long.
4. When `make start` prints the time, keep the file `deploy/docker/first-process.json`. It
   holds times and the kind of machine, and no account key.
5. Note the network: a home line, an office line or a mobile connection.
6. Put the file's content, the places they stopped and the network into the issue, and answer
   with the sentence "NEED-0034: provided".

## 5. What it must never be

Never the person's name, or anything that tells who they are, in the repository, an issue or a
log (principle 14). Never the account key the install printed. The trial measures the path, not
the person.

## 6. What happens next

A session adds the trial to `docs/runs/first-process-in-ten-minutes.md`: the time, the machine,
the network, and every place the person stopped, each fixed or recorded as a finding. At ten
minutes or less UC-10.4's last condition holds and #405 closes. Above ten minutes the time is
reported as it was, with where it went, and #405 stays open for what makes the path shorter.

## 7. How to confirm

```bash
grep -c "With a person" docs/runs/first-process-in-ten-minutes.md
```

The section exists from the start; once the trial is reported, it names a time instead of
"not yet".
