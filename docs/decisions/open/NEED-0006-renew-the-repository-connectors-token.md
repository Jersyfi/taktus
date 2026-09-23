# NEED-0006 — Renew the repository connector's token

**Kind:** credential
**Raised in:** [#23](https://github.com/Jersyfi/taktus/pull/23), which wires the three credentials and raises their renewals
**Issue:** [#25](https://github.com/Jersyfi/taktus/issues/25)
**Needed by:** 2026-12-14
**Foreseeable since:** [#23](https://github.com/Jersyfi/taktus/pull/23), the pull request that wired the token and read its validity; raised the same day

## 1. What is needed

A new fine-grained personal access token for this repository, with exactly the settings of the
one provided under NEED-0002, written into the same file — and the old token deleted
afterwards. The token provided on 2026-09-22 was issued for 90 days. It stops working on
**2026-12-21**. This request asks for the replacement one week before that.

## 2. Why

Every read and every write Taktus makes against this repository goes through it: P-02 reads
issue and comments and writes the acceptance criteria; P-03 reads them again, creates the
branch with the coding worker's commit, reads the pipeline's verdict, opens the pull request
and sets its label. With the token expired, the connector refuses every call
`unauthenticated` and the first step of either process fails.

The renewal is raised now rather than in December because the expiry was known the moment the
token was wired. That is the timing rule of ADR-0028: foreseeable, not blocking.

## 3. By when

**2026-12-14**, one week before the expiry on 2026-12-21.

If it is not there by then, the behaviour is the one stated in NEED-0005 §3 and it holds for
every credential of this repository: Taktus **halts at a step boundary with the cause, never
aborts, and never retries silently.** For this token specifically, the connector contract makes
it concrete: a call refused by the hosting service ends with cause `unauthenticated` and effect
`none`, and `unauthenticated` is not retryable — the conformance suite checks both (C-03,
`src/taktus/conformance/connector/rules.py`). So an expired token cannot leave a half-written
branch or a duplicate pull request behind: the refusal happens before the service does
anything, the step fails, the run escalates at that boundary, and a new token in the same file
plus a resume continues where it stopped.

## 4. How to provide it

The same steps as NEED-0002 §4, with a deletion at the end. Fifteen minutes.

1. GitHub → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained
   tokens* → *Generate new token*.
2. **Name:** "taktus connector, from 2026-12". **Expiration:** 90 days again, unless you want
   a different rhythm; note the date either way. **Resource owner:** you. **Repository
   access:** *Only select repositories* → `Jersyfi/taktus`, and no other.
3. **Permissions**, exactly these, under *Repository permissions*; every other one at *No
   access*. They are the permissions the two processes use and no more — the same table as
   NEED-0002 §4, repeated here so that this request stands on its own:

   | Permission | Access | Used by |
   |---|---|---|
   | Contents | Read and write | the branch, the commit and the tree P-03 creates |
   | Pull requests | Read and write | P-03 opens the pull request; both processes look up existing ones |
   | Issues | Read and write | P-02 reads the issue and writes the criteria as a comment; P-03 sets the label |
   | Actions | Read | P-03 reads the pipeline's verdict on the branch |
   | Metadata | Read | set by GitHub automatically |

   No *Workflows*, no *Administration*, no organisation permissions. A renewal is the moment
   at which a token quietly grows: if a run failed in the meantime for lack of a permission,
   that is a change to the process's declaration and to `CREDENTIALS.md` first, and a wider
   token second — never the other way round.
4. Generate; GitHub shows the value once. Write it into the file already in use, replacing its
   content: `~/.config/taktus/repository-token`, named in `.env` by
   `TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE`. An editor, not a command line. Then:

   ```bash
   chmod 600 ~/.config/taktus/repository-token
   ```

   Nothing in `.env` changes; the path is the same.
5. Confirm with section 7, then **delete the old token** under *Fine-grained tokens*.
6. **Note the new expiry** and say it when you close the issue, so that the next renewal is
   raised with its date.

## 5. What it must never be

- **Never pasted into a chat, a session, an issue or a pull request.** A session that needs the
  connector to act tells you which file to write; it never asks for the value.
- **Never committed**, in any file; `.env` is ignored by git and stays ignored.
- **Never on a command line** or in your shell's environment: only `tools/first_run.sh` reads
  the file, and only into the connector's own process.
- **Never broader than the table in section 4.** A token with more scopes than the processes
  declare lets a process do what its declaration does not say.
- **Never for a second repository**, and never a second file beside the old one.

Where it goes instead: the file this request names, whose path is already in `.env`.

## 6. What happens next

Nothing has to be told to anybody: the path in `.env` is unchanged, so the next run uses the
new token. Close issue [#25](https://github.com/Jersyfi/taktus/issues/25) with the sentence
**"NEED-0006 is provided; the file holds a new token and the old one is deleted"**, with the
new expiry date. The next session confirms with section 7, records the outcome here, and
raises the following renewal with that date.

When the identity component of `0.2.0` gives Taktus an identity of its own, this token is
replaced by that identity's token under a new needs request, and this one is deleted rather
than renewed.

## 7. How to confirm

Without revealing the value — the file is present, and the token reaches the repository.
`200` means it does:

```bash
test -s "$(sed -n 's/^TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE=//p' .env)" && echo "repository token file: present"
```

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.github.com/repos/Jersyfi/taktus \
  -H "Authorization: Bearer $(cat "$(sed -n 's/^TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE=//p' .env)")"
```

The scope is confirmed where it was set, and only there: GitHub → *Fine-grained tokens* → the
token → the repository list shows `Jersyfi/taktus` alone and the permissions read as the table
in section 4. A token cannot be asked through the API what it is allowed to do, so this half
is yours and cannot be checked by a session.
