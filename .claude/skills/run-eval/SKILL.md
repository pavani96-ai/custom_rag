---
name: run-eval
description: Build the eval dataset from the demo PDF and score the running API. Costs paid Gemini and Jina calls.
disable-model-invocation: true
model: haiku
effort: low
---

1. Confirm `make up` is running and the API answers on 127.0.0.1:8000.
2. Run `make eval-dataset`, then `make eval-run`.
3. Report the metric averages and any failed questions. Do not edit files.
