from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Optional

from deveval.core import RunConfig, diff_runs, parse_metric, run_eval
from deveval.reporting import render_markdown_report
from deveval.storage import DevEvalStorage


def format_run_summary(run_payload: dict) -> str:
    s = run_payload["summary"]
    lines = [
        f"run_id: {run_payload['run_id']}",
        f"quality: {s['quality']:.3f}",
        f"cases: {int(s['cases'])}, pass_count: {int(s['pass_count'])}",
        f"latency_p50_ms: {s['latency_p50_ms']:.2f}",
        f"latency_p95_ms: {s['latency_p95_ms']:.2f}",
        f"total_cost_usd: {s['total_cost_usd']:.6f}",
        f"cache_hit_rate: {s['cache_hit_rate']:.3f}",
    ]
    return "\n".join(lines)


def add_workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root. Artifacts are stored in .deveval/",
    )


def evaluate_run_gate(
    run_payload: dict,
    *,
    min_quality: Optional[float],
    max_latency_p50_ms: Optional[float],
    max_total_cost_usd: Optional[float],
    max_quality_drop: Optional[float],
    baseline_delta: Optional[dict],
) -> list[str]:
    summary = run_payload["summary"]
    failures: list[str] = []

    quality = float(summary["quality"])
    latency = float(summary["latency_p50_ms"])
    total_cost = float(summary["total_cost_usd"])

    if min_quality is not None and quality < min_quality:
        failures.append(f"quality {quality:.3f} fell below minimum {min_quality:.3f}")

    if max_latency_p50_ms is not None and latency > max_latency_p50_ms:
        failures.append(f"latency_p50_ms {latency:.2f} exceeded limit {max_latency_p50_ms:.2f}")

    if max_total_cost_usd is not None and total_cost > max_total_cost_usd:
        failures.append(f"total_cost_usd {total_cost:.6f} exceeded limit {max_total_cost_usd:.6f}")

    if max_quality_drop is not None and baseline_delta is not None:
        delta_quality = float(baseline_delta["delta_quality"])
        if delta_quality < 0 and abs(delta_quality) > max_quality_drop:
            failures.append(
                f"quality dropped by {abs(delta_quality):.3f}, exceeding limit {max_quality_drop:.3f}"
            )

    return failures


def cmd_run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    storage = DevEvalStorage(workspace / ".deveval")

    api_key = args.api_key or os.getenv("DEVEVAL_API_KEY")

    config = RunConfig(
        provider=args.provider,
        model=args.model,
        prompt_template=args.prompt_template,
        metric=parse_metric(args.metric),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        input_cost_per_1k=args.input_cost_per_1k,
        output_cost_per_1k=args.output_cost_per_1k,
        api_url=args.api_url,
        api_key=api_key,
    )

    run = run_eval(Path(args.dataset), config, storage)
    run_payload = run.__dict__
    print(format_run_summary(run_payload))

    if args.set_baseline:
        storage.set_baseline(args.set_baseline, run.run_id)
        print(f"baseline_set: {args.set_baseline} -> {run.run_id}")

    if args.compare_baseline:
        baseline_run_id = storage.get_baseline_run_id(args.compare_baseline)
        base = storage.load_run(baseline_run_id)
        cur = storage.load_run(run.run_id)
        delta = diff_runs(base, cur)
        print("delta_quality: {:.3f}".format(delta["delta_quality"]))
        print("delta_latency_p50_ms: {:.2f}".format(delta["delta_latency_p50_ms"]))
        print("delta_total_cost_usd: {:.6f}".format(delta["delta_total_cost_usd"]))
        print("delta_cache_hit_rate: {:.3f}".format(delta["delta_cache_hit_rate"]))

    failures = evaluate_run_gate(
        run_payload,
        min_quality=args.min_quality,
        max_latency_p50_ms=args.max_latency_p50_ms,
        max_total_cost_usd=args.max_total_cost_usd,
        max_quality_drop=args.max_quality_drop,
        baseline_delta=delta if args.compare_baseline else None,
    )
    if failures:
        for failure in failures:
            print(f"gate_failed: {failure}", file=sys.stderr)
        return 1

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    storage = DevEvalStorage(workspace / ".deveval")

    base_run_id = storage.get_baseline_run_id(args.baseline)
    base = storage.load_run(base_run_id)

    current_run_id: Optional[str] = args.run_id
    if not current_run_id:
        raise ValueError("--run-id is required for diff")

    cur = storage.load_run(current_run_id)
    delta = diff_runs(base, cur)

    print(f"baseline: {args.baseline} ({base_run_id})")
    print(f"current: {current_run_id}")
    print("delta_quality: {:.3f}".format(delta["delta_quality"]))
    print("delta_latency_p50_ms: {:.2f}".format(delta["delta_latency_p50_ms"]))
    print("delta_total_cost_usd: {:.6f}".format(delta["delta_total_cost_usd"]))
    print("delta_cache_hit_rate: {:.3f}".format(delta["delta_cache_hit_rate"]))
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    storage = DevEvalStorage(workspace / ".deveval")
    runs = storage.list_runs()

    if not runs:
        print("No runs found.")
        return 0

    for run in runs[: args.limit]:
        summary = run.get("summary", {})
        print(
            f"{run.get('run_id')} | provider={run.get('config', {}).get('provider')} "
            f"| model={run.get('config', {}).get('model')} "
            f"| quality={float(summary.get('quality', 0.0)):.3f} "
            f"| cost={float(summary.get('total_cost_usd', 0.0)):.6f}"
        )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    storage = DevEvalStorage(workspace / ".deveval")
    run = storage.load_run(args.run_id)
    markdown = render_markdown_report(run)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(markdown, encoding="utf-8")
        print(f"report_written: {output_path.as_posix()}")
        return 0

    print(markdown, end="")
    return 0


def cmd_baseline_list(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    storage = DevEvalStorage(workspace / ".deveval")
    baselines = storage.list_baselines()
    if not baselines:
        print("No baselines found.")
        return 0
    for name, run_id in sorted(baselines.items()):
        print(f"{name}: {run_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deveval",
        description="Local-first LLM evaluation runner with baselines, diffs, and caching.",
    )
    add_workspace_arg(p)

    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run evaluation dataset")
    add_workspace_arg(run_p)
    run_p.add_argument("--dataset", required=True, help="Path to JSONL dataset")
    run_p.add_argument("--provider", required=True, choices=["mock", "openai_compat"])
    run_p.add_argument("--model", required=True, help="Model name")
    run_p.add_argument("--prompt-template", required=True, help="System/prefix prompt")
    run_p.add_argument("--metric", default="contains", help="Metric format: exact | contains:<needle> | starts_with:<prefix>")
    run_p.add_argument("--temperature", type=float, default=0.0)
    run_p.add_argument("--max_tokens", type=int, default=300)
    run_p.add_argument("--input-cost-per-1k", type=float, default=0.005)
    run_p.add_argument("--output-cost-per-1k", type=float, default=0.015)
    run_p.add_argument("--api-url", default=None, help="Required for openai_compat")
    run_p.add_argument("--api-key", default=None, help="API key or use DEVEVAL_API_KEY")
    run_p.add_argument("--set-baseline", default=None, help="Set baseline name for this run")
    run_p.add_argument("--compare-baseline", default=None, help="Compare this run against baseline name")
    run_p.add_argument("--min-quality", type=float, default=None, help="Exit nonzero if quality falls below this value.")
    run_p.add_argument(
        "--max-latency-p50-ms",
        type=float,
        default=None,
        help="Exit nonzero if p50 latency exceeds this value.",
    )
    run_p.add_argument(
        "--max-total-cost-usd",
        type=float,
        default=None,
        help="Exit nonzero if total cost exceeds this value.",
    )
    run_p.add_argument(
        "--max-quality-drop",
        type=float,
        default=None,
        help="When comparing against a baseline, exit nonzero if quality drops by more than this amount.",
    )
    run_p.set_defaults(func=cmd_run)

    diff_p = sub.add_parser("diff", help="Compare an existing run against a baseline")
    add_workspace_arg(diff_p)
    diff_p.add_argument("--baseline", required=True)
    diff_p.add_argument("--run-id", required=True)
    diff_p.set_defaults(func=cmd_diff)

    baseline_p = sub.add_parser("baselines", help="List baselines")
    add_workspace_arg(baseline_p)
    baseline_p.set_defaults(func=cmd_baseline_list)

    runs_p = sub.add_parser("runs", help="List recent runs")
    add_workspace_arg(runs_p)
    runs_p.add_argument("--limit", type=int, default=10)
    runs_p.set_defaults(func=cmd_runs)

    report_p = sub.add_parser("report", help="Render a markdown report for a run")
    add_workspace_arg(report_p)
    report_p.add_argument("--run-id", required=True)
    report_p.add_argument("--output", default=None, help="Write markdown output to a file")
    report_p.set_defaults(func=cmd_report)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.func(args))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
