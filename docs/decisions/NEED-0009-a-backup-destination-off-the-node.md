# NEED-0009 — A backup destination off the node

**Kind:** access
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**Issue:** [#53](https://github.com/Jersyfi/taktus/issues/53)
**Needed by:** 2026-10-27
**Foreseeable since:** [#40](https://github.com/Jersyfi/taktus/pull/40), whose deployment plan deferred backups to "its own pull request and its own needs request" (`deploy/k8s/README.md` §9); raised late, on 2026-10-01, after the audit of the register found it never was

## 1. What is needed

A place to write the Taktus database's backups that is **not the machine the database runs
on**, and a credential for it that may write and read there but **may not delete**.

The place is yours to choose: storage on another machine you control, or an object store at a
provider in the European Union (principle 11). What it must offer is in section 4.

## 2. Why

The database is Taktus's single source of truth. It holds what runs, what has run, the ledger
with its chain of every step, and the provenance of every result. Nothing else holds them.

On the target platform the database's volume uses a storage class that binds it to **one node**.
A disk failure on that node loses the ledger, and with it the answer to "what did Taktus do, and
since when has it been wrong?" (ADR-0021). A snapshot on the same disk does not help: it fails
with the disk.

ADR-0013 C requires that Taktus is repairable without Taktus: a manual way to restore an earlier
version, documented and exercised. A restore needs something to restore from, kept somewhere a
failure of the node does not reach.

## 3. By when

**2026-10-27**, a week after the kubeconfig (NEED-0007) and the public name (NEED-0008), so that
the backup pull request can be written and its restore exercised before Taktus runs on the
platform for real.

If it is not there by then, this stands still:

- **The instance holds no real work.** It may be installed and tried; it does not run processes
  whose results anyone relies on, because a node failure would lose them without a trace.
- **ADR-0013 C stays unmet** for the deployed instance: the restore path is written, but cannot
  be exercised against a real backup.
- **Autonomy is not raised** for any process on that instance: level 3 and 4 presuppose that
  Taktus is repairable (ADR-0013).

## 4. How to provide it

Everything below is done by you, once. Nothing in it is a value this repository ever sees.

1. **Choose the place**, off the node. Either another machine you control, reachable from the
   cluster, or an object store at a provider in the European Union.
2. **Create a location for Taktus alone** there — a bucket, or a directory — that nothing else
   writes into.
3. **Turn on retention or object lock** if the place offers it, so that a written backup cannot
   be removed before its retention ends. This is what makes the next step's restriction hold.
4. **Create a credential that may write, list and read in that location and may not delete.**
   An instance that has been compromised must not be able to erase its own history.
5. **Write the credential to a file readable by you alone**, and keep it in your own secret
   store, next to the platform's other secrets:

   ```bash
   chmod 600 <the file>
   ```

6. **Put the place's address in your private note**, not in this repository: it is one
   deployment's name, and this repository is public.
7. **Tell the repository where the credential is**, by path and never by content, in `.env`:

   ```bash
   TAKTUS_CREDENTIAL_BACKUP_STORE_FILE=<the path>
   ```

   The name follows the one pattern every credential follows (`CREDENTIALS.md`, DEC-0018).

## 5. What it must never be

- **Never on the node the database runs on**, and never on the same disk by another path.
- **Never a credential that may delete** what it wrote. Write, list and read only.
- **Never pasted into a chat, a session, an issue or a pull request**, and never committed. A
  session that receives it cannot un-receive it, and this repository is public.
- **Never the place's address in this repository.** It belongs in your private note.

Where it goes instead: your secret store, the file of step 5, and its path in `.env`.

## 6. What happens next

Tell the session: **"NEED-0009 is provided; the credential is named in `.env`, the place is in
the private note."** The backup pull request then adds a scheduled backup of the database to
that place, and writes the restore as a procedure a person carries out without Taktus
(ADR-0013 C). The restore is exercised once, into an empty database, before the instance holds
real work, and the trial is recorded under `docs/runs/`. How long a backup is kept is a limit
and is asked in that pull request (M3.10).

## 7. How to confirm

Without revealing anything, with the place's own client and the credential of step 4:

- listing the location succeeds;
- writing a test object succeeds;
- deleting that test object is **refused**.

A deletion that succeeds means the credential is wider than this need, and it is narrowed
before anything is backed up with it.

## Outcome

**Provided:** 2026-10-08
**Confirmed by:** with the credential, the bucket was listed (empty), an object was written, read
back and deleted. Nothing from the credential file was printed. Versioning and object lock are
off, as decided.
**How it was provided:** a bucket at the owner's object-storage provider in the European Union,
with a credential that may list, write, read and delete, in a file readable by the owner alone;
the session also stored it as a secret in the control plane's namespace for the backup job. The
owner decided against object lock and a fixed retention at the store (DEC-0058): **Taktus manages
the retention itself, configurable, 30 days by default, and encryption is an option Taktus offers,
off by default.** So section 1's "may not delete" and section 4's steps 3 and 4 no longer hold:
the credential may delete, and an instance that is compromised could delete its own backups. The
place's location and name are in the owner's private note.
**Recorded in:** [#97](https://github.com/Jersyfi/taktus/pull/97); the backup task carries the
retention and the encryption option
