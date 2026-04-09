# DevEval report: run_example

## Summary

- Provider: `mock`
- Model: `mock-v1`
- Dataset: `examples/support_eval.jsonl`
- Quality: `0.333`
- Cases: `3`
- Pass count: `1`
- P50 latency: `0.01 ms`
- P95 latency: `0.01 ms`
- Total cost: `$0.000735`
- Cache hit rate: `1.000`

## Case results

| Case ID | Passed | Score | Latency (ms) | Cost (USD) | Cache |
| --- | --- | --- | ---: | ---: | --- |
| 1 | yes | 1.0 | 0.01 | 0.000245 | hit |
| 2 | no | 0.0 | 0.01 | 0.000245 | hit |
| 3 | no | 0.0 | 0.00 | 0.000245 | hit |
