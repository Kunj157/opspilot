# Agent evaluations

Fixed datasets that `make test-agent` runs against a real database, the real
embedding model, and canned telemetry. Results go to
`test-results/agent-evals/`.

| Dataset | What it checks |
|---|---|
| `retrieval.json` | The right runbook ranks first for each demo incident; a prompt-injection runbook never does |
| `investigations.json` | The full investigation workflow: suspected service, tools called, runbook found, hypotheses grounded in evidence, remediation proposed, and that no forbidden action or target is ever proposed |

`make test-agent` uses a scripted model (CI). Its proposal for each case is
deliberately naive, including a namespace deletion requested by an injected
runbook, a restart outside the allowed namespaces, and a pause of a rollout
that already finished, so the remediation policy is what keeps it safe. `make test-agent LLM=ollama` (after
`make llm-up`) runs the same cases on the local model. With a real model only
safety and groundedness are enforced; the scores are recorded.

Last local run (qwen2.5 7B instruct, RTX 4090): service, runbook, hypothesis,
and remediation accuracy 100 %, tool accuracy 93.8 %, groundedness 100 %,
0 unsafe proposals, 7.7 s and about 4,100 tokens per investigation.
