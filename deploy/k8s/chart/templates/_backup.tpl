{{/*
What the backup, the archive of the write-ahead log and the drill share (ADR-0087, ADR-0174): the
store's settings as variables, its credential as mounted files, and the egress to it.
*/}}

{{/* Whether the database archives its write-ahead log: refused where it cannot. */}}
{{- define "taktus.pointInTime" -}}
{{- if .Values.backup.pointInTime.enabled -}}
{{- if not .Values.backup.enabled -}}
{{- fail "backup.pointInTime.enabled needs backup.enabled: the base backups are taken by the backup's CronJob" -}}
{{- end -}}
{{- if not .Values.database.deploy -}}
{{- fail "backup.pointInTime.enabled needs database.deploy: an external server archives its log by its own operator's means" -}}
{{- end -}}
true
{{- end -}}
{{- end -}}

{{/* The store's settings and its credential's files, for a container's `env`. */}}
{{- define "taktus.backupStoreEnv" -}}
{{- $b := .Values.backup -}}
{{- $store := $b.store -}}
{{- $idKey := required "backup.store.accessKeyIdKey is required" $store.accessKeyIdKey -}}
{{- $secretKey := required "backup.store.secretKey is required" $store.secretKey -}}
- name: TAKTUS_BACKUP_STORE_ENDPOINT
  value: {{ required "backup.store.endpoint is required" $store.endpoint | quote }}
- name: TAKTUS_BACKUP_STORE_REGION
  value: {{ $store.region | quote }}
- name: TAKTUS_BACKUP_STORE_BUCKET
  value: {{ required "backup.store.bucket is required" $store.bucket | quote }}
- name: TAKTUS_BACKUP_STORE_PREFIX
  value: {{ $store.prefix | quote }}
- name: TAKTUS_CREDENTIAL_BACKUP_STORE_ACCESS_KEY_ID_FILE
  value: {{ printf "/run/secrets/taktus/backup-store/%s" $idKey | quote }}
- name: TAKTUS_CREDENTIAL_BACKUP_STORE_FILE
  value: {{ printf "/run/secrets/taktus/backup-store/%s" $secretKey | quote }}
- name: TAKTUS_BACKUP_RETENTION_DAYS
  value: {{ $b.retentionDays | quote }}
- name: TAKTUS_BACKUP_RECIPIENT
  value: {{ $b.recipient | quote }}
{{- end -}}

{{/* The store's credential as a volume of two files. */}}
{{- define "taktus.backupStoreVolume" -}}
{{- $store := .Values.backup.store -}}
- name: backup-store
  secret:
    secretName: {{ required "backup.store.secret is required: the Secret holding the store's credential" $store.secret }}
    defaultMode: 0440
    items:
      - key: {{ $store.accessKeyIdKey }}
        path: {{ $store.accessKeyIdKey }}
      - key: {{ $store.secretKey }}
        path: {{ $store.secretKey }}
{{- end -}}

{{/* Egress to the store: outside the excluded ranges, on the backup's ports. */}}
{{- define "taktus.backupStoreEgress" -}}
{{- $v4 := list -}}
{{- $v6 := list -}}
{{- range .Values.execution.egress.exceptCidrs -}}
{{- if contains ":" . -}}{{- $v6 = append $v6 . -}}{{- else -}}{{- $v4 = append $v4 . -}}{{- end -}}
{{- end -}}
- to:
    - ipBlock:
        cidr: 0.0.0.0/0
        {{- with $v4 }}
        except: {{ toJson . }}
        {{- end }}
    - ipBlock:
        cidr: ::/0
        {{- with $v6 }}
        except: {{ toJson . }}
        {{- end }}
  ports:
    {{- range .Values.backup.egressPorts }}
    - { protocol: TCP, port: {{ . }} }
    {{- end }}
{{- end -}}

{{/*
The database's connection rules with point-in-time recovery: the image's own — trust on the
pod's own socket and loopback, a password from everywhere else — and one line more, a
replication connection with a password, which the backup's base backup is.
*/}}
{{- define "taktus.databaseHba" -}}
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
host    all             all             all                     scram-sha-256
host    replication     all             all                     scram-sha-256
{{- end -}}
