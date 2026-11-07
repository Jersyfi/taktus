# The backup image: the database's scheduled backup (ADR-0087, deploy/backup/backup.py).
#
# Built from the repository root:  docker build -f deploy/backup/Dockerfile .
# The base is the database's own image, so that pg_dump and psql are of the server's major
# version; the chart's `database.image` and this line move together. The three tools a person
# restoring by hand uses too are added from the distribution: python3 for the program, age for
# the optional encryption, rclone for the store. Nothing of Taktus is in it: a backup is taken
# while Taktus is faulty as well (ADR-0013 C).
#
# rclone and age come from their projects' releases, pinned by version and by the SHA-256 each
# release publishes per platform (rclone's SHA256SUMS, the digest of age's release asset), not
# from the distribution: the distribution's builds carried Go modules with fixed critical and high
# vulnerabilities, which the image scan of ADR-0173 (#347) refuses. A new version is a change to these
# lines, with its release's digests. The distribution's own packages are upgraded at build time.
FROM postgres:16-alpine AS rclone
ARG TARGETARCH
ARG RCLONE_VERSION=1.75.2
RUN set -eu; \
    arch="${TARGETARCH:-$(uname -m)}"; \
    case "$arch" in \
        amd64 | x86_64) arch=amd64; sum=349ac8fba6ff65d6247043f1750cdcb518ec5d500ef91463a10d37c0ccdf3702 ;; \
        arm64 | aarch64) arch=arm64; sum=7e1e8d69654941b7b7df84ee74c5f7fb09cce7d5496947fb7bf16b55ff427d10 ;; \
        *) echo "no pinned rclone for $arch" >&2; exit 1 ;; \
    esac; \
    wget -q -O /tmp/rclone.zip \
        "https://downloads.rclone.org/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-${arch}.zip"; \
    echo "$sum  /tmp/rclone.zip" | sha256sum -c -; \
    unzip -q /tmp/rclone.zip -d /tmp; \
    install -m 755 "/tmp/rclone-v${RCLONE_VERSION}-linux-${arch}/rclone" /usr/local/bin/rclone

FROM postgres:16-alpine AS age
ARG TARGETARCH
ARG AGE_VERSION=1.3.2
RUN set -eu; \
    arch="${TARGETARCH:-$(uname -m)}"; \
    case "$arch" in \
        amd64 | x86_64) arch=amd64; sum=cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10 ;; \
        arm64 | aarch64) arch=arm64; sum=6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4 ;; \
        *) echo "no pinned age for $arch" >&2; exit 1 ;; \
    esac; \
    wget -q -O /tmp/age.tar.gz \
        "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-${arch}.tar.gz"; \
    echo "$sum  /tmp/age.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/age.tar.gz -C /tmp; \
    install -m 755 /tmp/age/age /tmp/age/age-keygen /usr/local/bin/

FROM postgres:16-alpine
RUN apk upgrade --no-cache && apk add --no-cache python3
COPY --from=rclone /usr/local/bin/rclone /usr/local/bin/rclone
COPY --from=age /usr/local/bin/age /usr/local/bin/age-keygen /usr/local/bin/
COPY deploy/backup/backup.py /usr/local/bin/taktus-backup
# Where the single server's compose file keeps its backups (`schedule`, ADR-0222): a volume
# mounted here takes this owner, so that the program, which runs as the database's user, writes.
RUN install -d -o 70 -g 70 -m 700 /backups
# The postgres user of the Alpine image, as the database itself runs (chart: database.yaml).
USER 70
ENTRYPOINT ["python3", "/usr/local/bin/taktus-backup"]
CMD ["backup"]
