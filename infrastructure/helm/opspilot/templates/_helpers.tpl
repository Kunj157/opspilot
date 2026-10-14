{{- define "opspilot.labels" -}}
app.kubernetes.io/part-of: opspilot
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "opspilot.selector" -}}
app.kubernetes.io/name: {{ . }}
app.kubernetes.io/part-of: opspilot
{{- end }}

{{/* Restricted pod security: non-root, read-only root, no privileges. */}}
{{- define "opspilot.podSecurity" -}}
runAsNonRoot: true
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{- define "opspilot.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end }}

{{- define "opspilot.env" -}}
envFrom:
  - configMapRef:
      name: opspilot-config
  - secretRef:
      name: {{ .Values.existingSecret }}
{{- end }}

{{/* Canary 10% → 25% → 50% → 100%, analysed against Prometheus from the first step. */}}
{{- define "opspilot.canarySteps" -}}
analysis:
  startingStep: 1
  templates:
    - templateName: opspilot-api-health
steps:
  {{- range .Values.rollouts.steps }}
  - setWeight: {{ . }}
  - pause: { duration: {{ $.Values.rollouts.pause }} }
  {{- end }}
{{- end }}
