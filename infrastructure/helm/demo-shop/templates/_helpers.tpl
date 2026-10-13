{{- define "demo-shop.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: demo-shop
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ .root.Chart.Name }}-{{ .root.Chart.Version }}
{{- end -}}

{{- define "demo-shop.selector" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: demo-shop
{{- end -}}
