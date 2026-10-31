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

{{/*
The labels of a pod whose restart costs availability — the database's. Nothing in them changes
with a release: a label on a pod template that changes replaces the pod (issue #237).
*/}}
{{- define "taktus.stableLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: taktus
app.kubernetes.io/managed-by: {{ .Release.Service }}
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

{{/*
The connectors this release ships, each an image of its own (ADR-0158): the directories under
connectors/taktus_connectors/ that run as a module. tests/governance/test_chart.py holds this
list to that directory.
*/}}
{{- define "taktus.shippedConnectors" -}}
accounting anthropic aws bookstack einvoice github httpcheck mail openai prometheus sentry slack stripe vendor
{{- end -}}

{{/*
A shipped connector's image (ADR-0158): `<connectors.imagePrefix>-<name>`, by default beside the
control plane's as `<image.repository>-connector-<name>`, at the control plane's tag, because a
release builds and pushes them together (.github/workflows/images.yml). Call with
(dict "root" $ "name" "github").
*/}}
{{- define "taktus.connectorImage" -}}
{{- $shipped := splitList " " (include "taktus.shippedConnectors" .root) -}}
{{- if not (has .name $shipped) -}}
{{- fail (printf "%q is no connector this release ships; it ships %s" .name (join ", " $shipped)) -}}
{{- end -}}
{{- $repository := required "image.repository is required" .root.Values.image.repository -}}
{{- $prefix := .root.Values.connectors.imagePrefix | default (printf "%s-connector" $repository) -}}
{{- include "taktus.image" (dict "what" "image" "image" (dict "repository" (printf "%s-%s" $prefix .name) "tag" .root.Values.image.tag)) -}}
{{- end -}}

{{/*
The shipped connector an entry of `connectors.others` runs: its `connector`, or the `module` an
earlier release ran from the control plane's image — `taktus.adapters.driven.connectors.<name>`
— which now runs from the connector's own image, so that an installed instance's values keep
working (ADR-0158). Empty for an entry with an image of its own.
*/}}
{{- define "taktus.otherConnectorName" -}}
{{- if .connector -}}
{{- .connector -}}
{{- else if .module -}}
{{- $module := toString .module -}}
{{- $found := regexFind "^(taktus\\.adapters\\.driven\\.connectors|taktus_connectors)\\.[a-z][a-z0-9_]*$" $module -}}
{{- if not $found -}}
{{- fail (printf "connectors.others %s: module %q is no shipped connector's; give `connector: <name>`, or an image of its own" .name $module) -}}
{{- end -}}
{{- last (splitList "." $module) -}}
{{- end -}}
{{- end -}}

{{/* A unit's variables (ADR-0090), a map, as TAKTUS_EXECUTION_UNIT_ENV reads them: NAME=value
pairs, comma separated, in the order of their names. A value holds no comma, which separates
the pairs. Which names are refused is the daemon's to say, at its start. */}}
{{- define "taktus.unitEnv" -}}
{{- $pairs := list -}}
{{- range $name, $value := (.env | default dict) -}}
{{- if contains "," (toString $value) -}}
{{- fail (printf "%s: the value of %s holds a comma, which separates the pairs" $.what $name) -}}
{{- end -}}
{{- $pairs = append $pairs (printf "%s=%v" $name $value) -}}
{{- end -}}
{{- join "," $pairs -}}
{{- end -}}

{{/* credential.model_api_key → TAKTUS_CREDENTIAL_MODEL_API_KEY: the configuration key in capitals. */}}
{{- define "taktus.variable" -}}
{{- printf "TAKTUS_%s" (. | upper | replace "." "_" | replace "-" "_") -}}
{{- end -}}

{{/* The volume name of a credential: a DNS label derived from its parameter. */}}
{{- define "taktus.credentialVolume" -}}
{{- printf "cred-%s" (. | lower | replace "." "-" | replace "_" "-") | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* "true" when a worker runs as a Job in the cluster: the one kind, or a worker's own. */}}
{{- define "taktus.clusterExecution" -}}
{{- $found := eq .Values.execution.kind "cluster" -}}
{{- range .Values.execution.workers -}}
{{- if eq (default $.Values.execution.kind .kind) "cluster" -}}{{- $found = true -}}{{- end -}}
{{- end -}}
{{- if $found -}}true{{- end -}}
{{- end -}}

{{/* The egress gateway's Deployment and Service (gateway.yaml, ADR-0115). */}}
{{- define "taktus.gatewayName" -}}
{{- printf "%s-gateway" (include "taktus.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Every secret a control plane container reads, as (volume, secret, key, directory, variable). */}}
{{- define "taktus.secretFiles" -}}
{{- $files := list -}}
{{- $files = append $files (dict "volume" "database-url" "secret" (required "database.urlSecret is required: the Secret holding the connection URL" .Values.database.urlSecret) "key" (required "database.urlKey is required" .Values.database.urlKey) "dir" "/run/secrets/taktus/database-url" "variable" "TAKTUS_DATABASE_URL_FILE") -}}
{{- if .Values.telemetry.otlp.headersSecret -}}
{{- $files = append $files (dict "volume" "otlp-headers" "secret" .Values.telemetry.otlp.headersSecret "key" (required "telemetry.otlp.headersKey is required with headersSecret" .Values.telemetry.otlp.headersKey) "dir" "/run/secrets/taktus/otlp-headers" "variable" "TAKTUS_OTLP_HEADERS_FILE") -}}
{{- end -}}
{{- if include "taktus.clusterExecution" . -}}
{{- $g := .Values.execution.gateway -}}
{{- $files = append $files (dict "volume" "gateway-key" "secret" (include "taktus.gatewayKeySecret" .) "key" (include "taktus.gatewayKeyKey" .) "dir" "/run/secrets/taktus/gateway-key" "variable" "TAKTUS_EXECUTION_GATEWAY_KEY_FILE") -}}
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

{{/* The chat connector's MCP address inside the cluster, when it is deployed. */}}
{{- define "taktus.chatConnectorUrl" -}}
{{- printf "http://%s-connector-chat:%v/mcp" (include "taktus.fullname" .) .Values.connectors.chat.port -}}
{{- end -}}

{{/*
Every connector of `connectors.others`, checked: renders nothing and fails on the first entry
that cannot be deployed as written (README §2). A name is the deployment's suffix and a
capability its label in TAKTUS_CONNECTORS: each is unique, and neither repeats a built-in one.
*/}}
{{- define "taktus.checkConnectors" -}}
{{- $names := list "repository" "chat" -}}
{{- $labels := list -}}
{{- if .Values.connectors.repository.enabled }}{{- $labels = append $labels "channel.repo" -}}{{- end -}}
{{- if .Values.connectors.chat.enabled }}{{- $labels = append $labels "channel.chat" -}}{{- end -}}
{{- range .Values.connectors.others -}}
{{- $name := required "connectors.others[].name is required" .name -}}
{{- if not (regexMatch "^[a-z][a-z0-9]*(-[a-z0-9]+)*$" $name) -}}
{{- fail (printf "connectors.others: %q is not a connector name: lowercase letters and digits, words joined by hyphens" $name) -}}
{{- end -}}
{{- if gt (len $name) 40 -}}
{{- fail (printf "connectors.others: %q is longer than 40 characters" $name) -}}
{{- end -}}
{{- if has $name $names -}}
{{- fail (printf "connectors.others: %q is named twice, or is a built-in connector's name" $name) -}}
{{- end -}}
{{- $names = append $names $name -}}
{{- $label := required (printf "connectors.others %s: capability is required: its label in TAKTUS_CONNECTORS" $name) .capability -}}
{{- if not (regexMatch "^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)*$" $label) -}}
{{- fail (printf "connectors.others %s: capability %q is not a dotted lowercase label" $name $label) -}}
{{- end -}}
{{- if has $label $labels -}}
{{- fail (printf "connectors.others %s: capability %q is another connector's label already" $name $label) -}}
{{- end -}}
{{- $labels = append $labels $label -}}
{{- $given := 0 -}}
{{- range list .connector .module .image -}}{{- if . }}{{- $given = add1 $given -}}{{- end -}}{{- end -}}
{{- if gt $given 1 -}}
{{- fail (printf "connectors.others %s: give one of connector, module or image, not both" $name) -}}
{{- end -}}
{{- if eq $given 0 -}}
{{- fail (printf "connectors.others %s: connector, module or image is required" $name) -}}
{{- end -}}
{{- if .image -}}
{{- $_ := include "taktus.imageRef" (dict "what" (printf "connectors.others %s image" $name) "ref" .image) -}}
{{- else -}}
{{- $_ := include "taktus.connectorImage" (dict "root" $ "name" (include "taktus.otherConnectorName" .)) -}}
{{- end -}}
{{- $port := required (printf "connectors.others %s: port is required" $name) .port -}}
{{- if or (lt (int $port) 1) (gt (int $port) 65535) -}}
{{- fail (printf "connectors.others %s: port %v is not a port" $name $port) -}}
{{- end -}}
{{- $credentials := list -}}
{{- range .credentials -}}
{{- $credential := required (printf "connectors.others %s: credentials[].name is required" $name) .name -}}
{{- if not (regexMatch "^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$" $credential) -}}
{{- fail (printf "connectors.others %s: credential %q is not a parameter name such as PAYMENTS_TOKEN" $name $credential) -}}
{{- end -}}
{{- if has $credential $credentials -}}
{{- fail (printf "connectors.others %s: credential %s is named twice" $name $credential) -}}
{{- end -}}
{{- $credentials = append $credentials $credential -}}
{{- $_ := required (printf "connectors.others %s: credential %s needs secret" $name $credential) .secret -}}
{{- $_ := required (printf "connectors.others %s: credential %s needs key" $name $credential) .key -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* A connector of `connectors.others` as TAKTUS_CONNECTORS names it: `label=url`. Call with (dict "root" $ "c" .). */}}
{{- define "taktus.otherConnectorEntry" -}}
{{- printf "%s=http://%s-connector-%s:%v/mcp" .c.capability (include "taktus.fullname" .root) .c.name .c.port -}}
{{- end -}}

{{- /* The profile: `standard` or `small`; anything else fails the render. */ -}}
{{- define "taktus.profile" -}}
{{- $p := .Values.profile | default "standard" -}}
{{- if not (has $p (list "standard" "small")) -}}
{{- fail (printf "profile must be standard or small, not %q" $p) -}}
{{- end -}}
{{- $p -}}
{{- end -}}

{{- /* The role label of the pod that serves the API. */ -}}
{{- define "taktus.apiRole" -}}
{{- ternary "all" "api" (eq (include "taktus.profile" .) "small") -}}
{{- end -}}

{{/* The Secret holding the egress gateway's key: the operator's, where `execution.gateway.keySecret`
names one; otherwise the one the chart creates and keeps (gateway-key.yaml, DEC-0216). */}}
{{- define "taktus.gatewayKeySecret" -}}
{{- .Values.execution.gateway.keySecret | default (printf "%s-gateway-key" (include "taktus.fullname" .)) -}}
{{- end -}}

{{- define "taktus.gatewayKeyKey" -}}
{{- if .Values.execution.gateway.keySecret -}}
{{- required "execution.gateway.keyKey is required with keySecret" .Values.execution.gateway.keyKey -}}
{{- else -}}
key
{{- end -}}
{{- end -}}
