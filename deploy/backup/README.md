# The backup image

The instance's database backup (ADR-0087): the database's own image with `python3`, `age` and
`rclone`, and one program of the standard library, `backup.py`, that imports nothing of Taktus.
The chart runs it as a CronJob (`backup.*`, `deploy/k8s/README.md` §11); the image workflow
builds it with the release images, and `tests/deploy/` runs it.

| File | What |
|---|---|
| `Dockerfile` | the image, built from the repository root: `docker build -f deploy/backup/Dockerfile .`. `rclone` and `age` come from their projects' releases, pinned by version and SHA-256 per platform; the distribution's builds carried fixed high and critical vulnerabilities, which the image scan of ADR-0173 (#347) refuses |
| `backup.py` | one run: the ledger heads and the schema revision read, `pg_dump`, with point-in-time recovery a base backup, the object store archived, optionally `age`, every object written and listed, then the retention kept, and last the run's outcome recorded in the database. Its configuration is in its docstring |

`backup.py backup` (the default) waits up to a minute for the database to accept connections — a
pod that has just started is refused for a few seconds while the cluster applies its network
policy — then takes a backup and keeps the retention; `backup.py list` lists
the store. The restore is not a command of this program: it is the steps of
`deploy/k8s/README.md` §11, with the tools of this image or any others, so that it needs nothing
the backup might have got wrong.

**Every run records its outcome** (ADR-0106). At its end, `backup.py backup` inserts one row
per tenant into the table `backup_outcome` of the database it backed up, through `psql` and
with the same login. A row holds the run's time, its name, `ok` or `failed`, and for a failure
the step that failed as a token: `configuration`, `database`, `encryption`, `objects`, `store`
or `retention`. It never holds a message. The instance reads the newest outcome and tells each
tenant's owner of a failed backup, or of one older than `TAKTUS_BACKUP_EXPECTED_HOURS`. A
recording that fails is printed and changes neither the backup nor the exit code. A run that
cannot reach the database, or whose database URL cannot be read, records nothing; the instance
then sees the backup as missing. The login must be allowed to insert into `backup_outcome`: the
database's superuser is; a login with `BYPASSRLS` needs `GRANT INSERT ON backup_outcome`.

**Point-in-time recovery and the drill** (ADR-0174). Three more commands of the same program, none
of which connects to the instance's database through a URL:

| Command | What |
|---|---|
| `archive-wal %p %f` | the database's `archive_command`: one finished segment of the write-ahead log into the store, under `wal/<system identifier>/`, encrypted where a recipient is set; a segment already there is not written again. It runs in the database's container, whose working directory is the data directory |
| `fetch-wal <system identifier> %f %p` | the matching `restore_command`; decrypts with `TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE` |
| `drill [--backup NAME] [--to MOMENT\|latest] [--heads FILE]` | S-03: restores a backup into a server of its own, in its working directory, with archiving off and no network address; recomputes every tenant's ledger chain by the ledger's published rule; holds it to the manifest's heads, and with `--heads` to the heads noted at the moment; writes `drills/taktus-<time>.drill.json`. Exit code 0 only for a verified restore |

`tests/deploy/test_point_in_time.py` runs all three against a database of its own;
`tests/deploy/test_drill_chain.py` holds the drill's chain check to Taktus's own verification.
