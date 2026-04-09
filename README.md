# Dev Eval Innovator

Local-first LLM evaluation runner for developers.

This project is a practical MVP for a real pain point:
- Prompt/model changes break behavior silently.
- Teams need reproducible eval runs.
- Teams need quality + latency + cost diffs before shipping.

## What it does

- Runs JSONL evaluation cases against a provider adapter.
- Caches provider responses by deterministic hash.
- Scores outputs with deterministic metrics.
- Stores run artifacts with stable metadata.
- Sets named baselines and compares future runs against them.
- Outputs terminal summaries for quick PR usage.
- Lists recent runs for quick inspection.
- Exports markdown reports from saved runs.
- Supports CI-style gates for quality, latency, cost, and baseline regression.

## Why this is useful

Developers can treat AI behavior like testable software:
- Create a baseline from a known-good run.
- Re-run after prompt/model changes.
- Fail fast when quality drops or cost/latency spikes.

## Installation

### Run directly from source

```bash
python -m deveval --help
```

### Install as a local CLI

```bash
pip install -e .
deveval --help
```

## Quick start

1) Create your dataset:

examples/support_eval.jsonl already included.

2) Run an evaluation:

python -m deveval run \
  --dataset examples/support_eval.jsonl \
  --provider mock \
  --model mock-v1 \
  --prompt-template "You are a helpful support assistant." \
  --metric contains:reset \
  --set-baseline support_v1

3) Make changes and run again:

python -m deveval run \
  --dataset examples/support_eval.jsonl \
  --provider mock \
  --model mock-v2 \
  --prompt-template "You are concise and strict." \
  --metric contains:reset

4) Diff against baseline:

python -m deveval diff --baseline support_v1 --run-id <new_run_id>

5) List recent runs:

python -m deveval runs --workspace .

6) Export a markdown report:

python -m deveval report --run-id <new_run_id> --output report.md

7) Inspect only failed cases from a run:

python -m deveval show --run-id <new_run_id> --failed-only --workspace .

8) Fail a CI run when quality drops:

python -m deveval run \
  --dataset examples/support_eval.jsonl \
  --provider mock \
  --model mock-v1 \
  --prompt-template "You are a helpful support assistant." \
  --metric contains:reset \
  --min-quality 0.80

## Project layout

- deveval/cli.py: command entry points and orchestration
- deveval/core.py: models, run engine, artifacts
- deveval/providers.py: provider adapters
- deveval/storage.py: cache, run files, baselines
- deveval/reporting.py: markdown report export
- examples/support_eval.jsonl: sample eval dataset
- docs/sample-report.md: sample generated report

## Provider support

- mock: deterministic local provider for development/testing
- openai_compat: generic OpenAI-compatible HTTP API

## Metrics

- `exact`
- `contains:<needle>`
- `starts_with:<prefix>`
- `regex:<pattern>`

## CI-friendly gates

The `run` command can exit nonzero when:

- quality is below `--min-quality`
- p50 latency exceeds `--max-latency-p50-ms`
- total cost exceeds `--max-total-cost-usd`
- quality regression against a baseline exceeds `--max-quality-drop`

Example:

```bash
python -m deveval run \
  --dataset examples/support_eval.jsonl \
  --provider mock \
  --model mock-v2 \
  --prompt-template "You are concise and strict." \
  --metric contains:reset \
  --compare-baseline support_v1 \
  --max-quality-drop 0.10
```

Sample output:

- [Sample markdown report](docs/sample-report.md)

For openai_compat, pass:
- --api-url
- --api-key (or set DEVEVAL_API_KEY)

## Example openai_compat run

python -m deveval run \
  --dataset examples/support_eval.jsonl \
  --provider openai_compat \
  --api-url https://api.openai.com/v1/chat/completions \
  --api-key "$DEVEVAL_API_KEY" \
  --model gpt-4o-mini \
  --prompt-template "You are a helpful support assistant." \
  --metric contains:reset

## Notes

- This MVP uses a simple cost estimate model (tokens * configured rates).
- It keeps all artifacts local in .deveval/.
- No external dependencies are required.
- `--workspace` can be placed either before or after the subcommand.
- The mock provider is intended for local workflow testing and deterministic demos.
