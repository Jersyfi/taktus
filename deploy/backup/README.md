# The backup image

The instance's database backup (ADR-0087): the database's own image with `python3`, `age` and
`rclone`, and one program of the standard library, `backup.py`, that imports nothing of Taktus.
The chart runs it as a CronJob (`backup.*`, `deploy/k8s/README.md` §11); the image workflow
builds it with the release images, and `tests/deploy/` runs it.

| File | What |
|---|---|
| `Dockerfile` | the image, built from the repository root: `docker build -f deploy/backup/Dockerfile .` |
| `backup.py` | one run: the ledger heads and the schema revision read, `pg_dump`, the object store archived, optionally `age`, every object written and listed, then the retention kept. Its configuration is in its docstring |

`backup.py backup` (the default) waits up to a minute for the database to accept connections — a
pod that has just started is refused for a few seconds while the cluster applies its network
policy — then takes a backup and keeps the retention; `backup.py list` lists
the store. The restore is not a command of this program: it is the steps of
`deploy/k8s/README.md` §11, with the tools of this image or any others, so that it needs nothing
the backup might have got wrong.
