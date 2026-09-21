# NEED-0002 — The repository connector's token

**Kind:** credential
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** [#19](https://github.com/Jersyfi/taktus/issues/19)
**Needed by:** 2026-10-05
**Foreseeable since:** [#8](https://github.com/Jersyfi/taktus/pull/8), which built the reference repository connector; stated as a note in #13, whose first run used the developer's own login instead

## 1. What is needed

A GitHub token, scoped to this one repository (`Jersyfi/taktus`) and to the few operations
the two processes use, with an expiry date. It is what the repository connector acts with when
Taktus reads an issue, writes a comment, creates a branch, opens a pull request, sets a label
or reads a pipeline's verdict. Taktus has no token of its own: it acts as the identity the
token belongs to, with that identity's permissions and no more.

## 2. Why

Every read and every write of the reference repository connector needs it. Process P-02
Refinement reads issue #11 and its comments and writes the acceptance criteria as a comment;
P-03 Implementation reads them again, creates the branch `taktus/issue-11` with the coding
worker's commit, reads the verdict of the pipeline on it, opens the pull request and labels it.
Without the token the connector ends every call `unauthenticated` without a request, and the
first step of either process fails.

The first run of 2026-09-19 used the developer's own login (`gh auth token`) for the length of
the run — every scope that login has, in a process environment. That was acceptable for a run
that wrote nothing, and it is not what the owner's run should use: the identity Taktus acts as
is provisional (DEC-0013) and is *you*, so the token is yours, but it must reach this
repository only and be able to do only what the processes do.

## 3. By when

**2026-10-05**, together with NEED-0001 and NEED-0003: the first live run needs all three, and
one without the others changes nothing.

If it is not there by then: the first live run waits (see NEED-0001 §3). A session could run
it with its own login again; it will not, because a pull request opened with a token that can
do more than the process declares is exactly the kind of "worked once, by hand" that this
project counts as unproven.

## 4. How to provide it

A **fine-grained personal access token** of your own GitHub account, limited to one repository.
(A separate machine account or a GitHub App would give Taktus an identity of its own; that is
the identity component of `0.2.0`, and it is not needed for the first run.)

1. GitHub → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained
   tokens* → *Generate new token*.
2. **Name:** "taktus connector". **Expiration:** 90 days (note the date; `CREDENTIALS.md` says a
   rotation is a new token for the same identity). **Resource owner:** you. **Repository access:** *Only select
   repositories* → `Jersyfi/taktus`, and no other.
3. **Permissions**, exactly these, under *Repository permissions*; leave every other one at
   *No access*:

   | Permission | Access | Used by |
   |---|---|---|
   | Contents | Read and write | the branch, the commit and the tree P-03 creates |
   | Pull requests | Read and write | P-03 opens the pull request; both processes look up existing ones |
   | Issues | Read and write | P-02 reads the issue and writes the criteria as a comment; P-03 sets the label |
   | Actions | Read | P-03 reads the pipeline's verdict on the branch |
   | Metadata | Read | set by GitHub automatically |

   No *Workflows* permission: the processes trigger no pipeline by hand (CI runs on a push to
   `taktus/**` on its own). No *Administration*, no organisation permissions.
4. Generate; GitHub shows the value once. Put it into a file readable by you alone, as in
   NEED-0001 §4 step 3:

   ```bash
   mkdir -p ~/.config/taktus && chmod 700 ~/.config/taktus
   ```

   create `~/.config/taktus/repository-token` with the value as its only content (an editor,
   not a command line), and:

   ```bash
   chmod 600 ~/.config/taktus/repository-token
   ```

5. Name the file in `.env` in the checkout (ignored by git):

   ```bash
   REPOSITORY_TOKEN_FILE=/Users/<you>/.config/taktus/repository-token
   ```

6. **Validity:** until the expiry you set. **Rotation:** before the expiry, and at once if it
   may have been seen — generate a new token with the same settings, write it into the file,
   delete the old one under *Fine-grained tokens*. `tools/first_run.sh` reads the file at start
   and hands the value to the connector process and to nothing else; nothing stores it.

## 5. What it must never be

- **Never pasted into a chat, a session, an issue or a pull request.** A session that needs the
  connector to act tells you which file to create; it never asks for the value.
- **Never committed**, in any file; `.env` is ignored by git and stays ignored.
- **Never on a command line** or in your shell's environment: only `tools/first_run.sh` reads
  the file, and only into the connector's own process.
- **Never broader than the table above.** A token with more scopes than the process declares
  would let a process do what its declaration does not say; the connector's declaration and
  `CREDENTIALS.md` are the permission, and the token must match them, not exceed them.
- **Never for a second repository.** A second tenant gets its own token under its own need.

Where it goes instead: the file of step 4, and its path in `.env`.

## 6. What happens next

With NEED-0001 and NEED-0003 also provided, the first live run:

```bash
tools/first_run.sh 11
```

P-03 opens a pull request for issue #11 under your name; CI decides; you merge or close it. The
sentence to the session: **"NEED-0002 is provided; the file is named in `.env`."** The session
confirms with section 7 and records the outcome in this record. When the identity component of
`0.2.0` gives Taktus an identity of its own, that pull request raises a new need for that
identity's token and this token is deleted.

## 7. How to confirm

Without revealing the value — the first command prints `present`, the second an HTTP status,
where `200` means the token reaches the repository:

```bash
test -s "$(sed -n 's/^REPOSITORY_TOKEN_FILE=//p' .env)" && echo "repository token file: present"
```

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.github.com/repos/Jersyfi/taktus \
  -H "Authorization: Bearer $(cat "$(sed -n 's/^REPOSITORY_TOKEN_FILE=//p' .env)")"
```

The scope is confirmed where it was set: GitHub → *Fine-grained tokens* → the token → the
repository list shows `Jersyfi/taktus` alone and the permissions read as the table in section
4. `tools/first_run.sh` checks the file's presence itself before it starts anything.
