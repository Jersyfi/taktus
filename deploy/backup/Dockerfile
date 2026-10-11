# The backup image: the database's scheduled backup (ADR-0087, deploy/backup/backup.py).
#
# Built from the repository root:  docker build -f deploy/backup/Dockerfile .
# The base is the database's own image, so that pg_dump and psql are of the server's major
# version; the chart's `database.image` and this line move together. The three tools a person
# restoring by hand uses too are added from the distribution: python3 for the program, age for
# the optional encryption, rclone for the store. Nothing of Taktus is in it: a backup is taken
# while Taktus is faulty as well (ADR-0013 C).
FROM postgres:16-alpine
RUN apk add --no-cache python3 age rclone
COPY deploy/backup/backup.py /usr/local/bin/taktus-backup
# The postgres user of the Alpine image, as the database itself runs (chart: database.yaml).
USER 70
ENTRYPOINT ["python3", "/usr/local/bin/taktus-backup"]
CMD ["backup"]
