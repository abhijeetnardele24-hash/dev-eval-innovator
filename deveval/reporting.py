from __future__ import annotations

from typing import Dict, List


def _format_money(value: float) -> str:
    return f"{value:.6f}"


def render_markdown_report(run_payload: Dict[str, object]) -> str:
    summary = run_payload["summary"]
    config = run_payload["config"]
    cases: List[Dict[str, object]] = list(run_payload["cases"])

    lines = [
        f"# DevEval report: {run_payload['run_id']}",
        "",
        "## Summary",
        "",
        f"- Provider: `{config['provider']}`",
        f"- Model: `{config['model']}`",
        f"- Dataset: `{run_payload['dataset_path']}`",
        f"- Quality: `{float(summary['quality']):.3f}`",
        f"- Cases: `{int(summary['cases'])}`",
        f"- Pass count: `{int(summary['pass_count'])}`",
        f"- P50 latency: `{float(summary['latency_p50_ms']):.2f} ms`",
        f"- P95 latency: `{float(summary['latency_p95_ms']):.2f} ms`",
        f"- Total cost: `${_format_money(float(summary['total_cost_usd']))}`",
        f"- Cache hit rate: `{float(summary['cache_hit_rate']):.3f}`",
        "",
        "## Case results",
        "",
        "| Case ID | Passed | Score | Latency (ms) | Cost (USD) | Cache |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]

    for case in cases:
        lines.append(
            "| {case_id} | {passed} | {score:.1f} | {latency:.2f} | {cost} | {cache_hit} |".format(
                case_id=case["case_id"],
                passed="yes" if case["passed"] else "no",
                score=float(case["score"]),
                latency=float(case["latency_ms"]),
                cost=_format_money(float(case["cost_usd"])),
                cache_hit="hit" if case["cache_hit"] else "miss",
            )
        )

    return "\n".join(lines) + "\n"
