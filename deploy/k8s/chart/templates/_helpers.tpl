{{/*
Shared names, labels and checks. Every object carries the standard labels; a pod's component
label is what the network policies select on.
*/}}

{{- define "taktus.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "taktus.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/part-of: taktus
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* The labels a selector uses: stable across upgrades. Call with (dict "root" $ "component" "x"). */}}
{{- define "taktus.selector" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "taktus.controlPlaneNamespace" -}}
{{- .Release.Namespace -}}
{{- end -}}

{{- define "taktus.executionNamespace" -}}
{{- required "execution.namespace is required: the execution namespace's name" .Values.execution.namespace -}}
{{- end -}}

{{- define "taktus.serviceAccount" -}}
{{- include "taktus.fullname" . -}}
{{- end -}}

{{/*
An image reference whose tag is a version. `latest`, an empty tag and a moving tag of that kind
are refused at render time: what runs must be what was released. Call with (dict "what" "image"
"image" .Values.image).
*/}}
{{- define "taktus.image" -}}
{{- $repository := required (printf "%s.repository is required" .what) .image.repository -}}
{{- $tag := toString (required (printf "%s.tag is required: the released version, never latest" .what) .image.tag) -}}
{{- if not (regexMatch "^v?[0-9]+(\\.[0-9]+)*([-+._][0-9A-Za-z.-]+)?$" $tag) -}}
{{- fail (printf "%s.tag %q is not a version; a tag such as latest moves under a running instance" .what $tag) -}}
{{- end -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}

{{/* An image given as one reference (repository:tag), held to the same rule. */}}
{{- define "taktus.imageRef" -}}
{{- $ref := toString .ref -}}
{{- $parts := regexFind ":[^:/]+$" $ref -}}
{{- if not $parts -}}
{{- fail (printf "%s %q names no tag; give the version explicitly" .what $ref) -}}
{{- end -}}
{{- include "taktus.image" (dict "what" .what "image" (dict "repository" (trimSuffix $parts $ref) "tag" (trimPrefix ":" $parts))) -}}
{{- end -}}

{{/* credential.model_api_key → TAKTUS_CREDENTIAL_MODEL_API_KEY: the configuration key in capitals. */}}
{{- define "taktus.variable" -}}
{{- printf "TAKTUS_%s" (. | upper | replace "." "_" | replace "-" "_") -}}
{{- end -}}

{{/* The volume name of a credential: a DNS label derived from its parameter. */}}
{{- define "taktus.credentialVolume" -}}
{{- printf "cred-%s" (. | lower | replace "." "-" | replace "_" "-") | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Every secret a control plane container reads, as (volume, secret, key, directory, variable). */}}
{{- define "taktus.secretFiles" -}}
{{- $files := list -}}
{{- $files = append $files (dict "volume" "database-url" "secret" (required "database.urlSecret is required: the Secret holding the connection URL" .Values.database.urlSecret) "key" (required "database.urlKey is required" .Values.database.urlKey) "dir" "/run/secrets/taktus/database-url" "variable" "TAKTUS_DATABASE_URL_FILE") -}}
{{- if .Values.telemetry.otlp.headersSecret -}}
{{- $files = append $files (dict "volume" "otlp-headers" "secret" .Values.telemetry.otlp.headersSecret "key" (required "telemetry.otlp.headersKey is required with headersSecret" .Values.telemetry.otlp.headersKey) "dir" "/run/secrets/taktus/otlp-headers" "variable" "TAKTUS_OTLP_HEADERS_FILE") -}}
{{- end -}}
{{- range .Values.credentials -}}
{{- $parameter := required "credentials[].parameter is required" .parameter -}}
{{- $dir := default (printf "/run/secrets/taktus/%s" $parameter) .mountPath -}}
{{- $files = append $files (dict "volume" (include "taktus.credentialVolume" $parameter) "secret" (required (printf "credentials %s: secret is required" $parameter) .secret) "key" (required (printf "credentials %s: key is required" $parameter) .key) "dir" $dir "variable" (printf "%s_FILE" (include "taktus.variable" $parameter))) -}}
{{- end -}}
{{- toJson $files -}}
{{- end -}}

{{/* The pod security context every pod of the chart runs under: the restricted profile. */}}
{{- define "taktus.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
capabilities:
  drop: [ALL]
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{/* The database volume's size in MiB, for the capacity report (DEC-0033). */}}
{{- define "taktus.databaseVolumeMb" -}}
{{- if .Values.capacity.databaseVolumeMb -}}
{{- .Values.capacity.databaseVolumeMb -}}
{{- else -}}
{{- $size := toString .Values.database.size -}}
{{- if hasSuffix "Ti" $size -}}{{- mul (trimSuffix "Ti" $size | atoi) 1048576 -}}
{{- else if hasSuffix "Gi" $size -}}{{- mul (trimSuffix "Gi" $size | atoi) 1024 -}}
{{- else if hasSuffix "Mi" $size -}}{{- trimSuffix "Mi" $size | atoi -}}
{{- else -}}{{- fail (printf "database.size %q: give it in Mi, Gi or Ti, or set capacity.databaseVolumeMb" $size) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* The repository connector's MCP address inside the cluster, when it is deployed. */}}
{{- define "taktus.repositoryConnectorUrl" -}}
{{- printf "http://%s-connector-repository:%v/mcp" (include "taktus.fullname" .) .Values.connectors.repository.port -}}
{{- end -}}
