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

{{/*
Canary 10% → 25% → 50% → 100%. The canary pods also get their own Service
(<name>-canary), which the smoke test calls right after the first weight;
the background analysis runs from that point on.
  dict "Values" .Values "service" $name "analysis" <template> "analysisUrls" <urls> "smokeUrls" <urls>
*/}}
{{- define "opspilot.canarySteps" -}}
canaryService: {{ .service }}-canary
{{- if .analysis }}
analysis:
  startingStep: 1
  templates:
    - templateName: {{ .analysis }}
  {{- with .analysisUrls }}
  args:
    - { name: urls, value: {{ . | quote }} }
  {{- end }}
{{- end }}
steps:
  {{- range $i, $weight := .Values.rollouts.steps }}
  - setWeight: {{ $weight }}
  {{- if and (eq $i 0) $.Values.smokeTest.enabled }}
  - analysis:
      templates:
        - templateName: opspilot-smoke
      args:
        - { name: urls, value: {{ $.smokeUrls | quote }} }
  {{- end }}
  - pause: { duration: {{ $.Values.rollouts.pause }} }
  {{- end }}
{{- end }}

{{/* A smoke-test Job spec: non-root, read-only root, runs files/smoke.py from the API image. */}}
{{- define "opspilot.smokeJob" -}}
{{- $ := .root -}}
backoffLimit: 0
activeDeadlineSeconds: 180
ttlSecondsAfterFinished: 3600
template:
  metadata:
    labels: {{- include "opspilot.selector" "opspilot-smoke" | nindent 6 }}
  spec:
    restartPolicy: Never
    serviceAccountName: opspilot-smoke
    automountServiceAccountToken: false
    securityContext: {{- include "opspilot.podSecurity" $ | nindent 6 }}
    containers:
      - name: smoke
        image: "{{ $.Values.image.api.repository }}:{{ $.Values.image.api.tag }}"
        imagePullPolicy: {{ $.Values.image.pullPolicy }}
        command: ["python", "/smoke/smoke.py", {{ .urls | quote }}]
        env:
          - { name: SMOKE_DEADLINE_SECONDS, value: {{ .deadline | default "90" | quote }} }
        resources:
          requests: { cpu: 10m, memory: 32Mi }
          limits: { cpu: 200m, memory: 128Mi }
        securityContext: {{- include "opspilot.containerSecurity" $ | nindent 10 }}
        volumeMounts:
          - { name: smoke, mountPath: /smoke, readOnly: true }
    volumes:
      - name: smoke
        configMap: { name: opspilot-smoke }
{{- end }}
