from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time
from typing import Dict, List, Optional

from deveval.providers import ProviderConfig, build_provider
from deveval.storage import DevEvalStorage


@dataclass
class EvalCase:
    case_id: str
    input_text: str
    expected: str
    metadata: Dict[str, str]


@dataclass
class MetricConfig:
    name: str
    arg: Optional[str] = None


@dataclass
class RunConfig:
    provider: str
    model: str
    prompt_template: str
    metric: MetricConfig
    temperature: float
    max_tokens: int
    input_cost_per_1k: float
    output_cost_per_1k: float
    api_url: Optional[str] = None
    api_key: Optional[str] = None

    def hash(self) -> str:
        payload = {
            "provider": self.provider,
            "model": self.model,
            "prompt_template": self.prompt_template,
            "metric": {"name": self.metric.name, "arg": self.metric.arg},
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "input_cost_per_1k": self.input_cost_per_1k,
            "output_cost_per_1k": self.output_cost_per_1k,
            "api_url": self.api_url,
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class CaseResult:
    case_id: str
    output: str
    expected: str
    passed: bool
    score: float
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_hit: bool


@dataclass
class RunResult:
    run_id: str
    started_at: str
    ended_at: str
    dataset_path: str
    config_hash: str
    config: Dict[str, object]
    summary: Dict[str, float]
    cases: List[Dict[str, object]]


def parse_metric(metric_raw: str) -> MetricConfig:
    raw = metric_raw.strip().lower()
    if not raw:
        raise ValueError("Metric cannot be empty.")

    if ":" in raw:
        name, arg = raw.split(":", 1)
        metric = MetricConfig(name=name.strip(), arg=arg.strip())
    else:
        metric = MetricConfig(name=raw)

    if metric.name not in {"exact", "contains", "starts_with", "regex"}:
        raise ValueError(
            f"Unsupported metric: {metric.name}. Use exact, contains:<needle>, starts_with:<prefix>, or regex:<pattern>."
        )

    return metric


def parse_dataset(dataset_path: Path) -> List[EvalCase]:
    cases: List[EvalCase] = []
    with dataset_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            case_id = str(obj.get("id", idx))
            input_text = str(obj["input"])
            expected = str(obj.get("expected", ""))
            metadata_obj = obj.get("metadata", {})
            metadata = {str(k): str(v) for k, v in metadata_obj.items()} if isinstance(metadata_obj, dict) else {}
            cases.append(EvalCase(case_id=case_id, input_text=input_text, expected=expected, metadata=metadata))
    return cases


def score_case(metric: MetricConfig, output: str, expected: str) -> tuple[bool, float]:
    output_l = output.strip().lower()
    expected_l = expected.strip().lower()

    if metric.name == "exact":
        passed = output_l == expected_l
        return passed, 1.0 if passed else 0.0

    if metric.name == "contains":
        needle = (metric.arg or expected).strip().lower()
        if not needle:
            return False, 0.0
        passed = needle in output_l
        return passed, 1.0 if passed else 0.0

    if metric.name == "starts_with":
        prefix = (metric.arg or expected).strip().lower()
        if not prefix:
            return False, 0.0
        passed = output_l.startswith(prefix)
        return passed, 1.0 if passed else 0.0

    if metric.name == "regex":
        pattern = (metric.arg or expected).strip()
        if not pattern:
            return False, 0.0
        passed = re.search(pattern, output, flags=re.IGNORECASE) is not None
        return passed, 1.0 if passed else 0.0

    return False, 0.0


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def estimate_cost(input_tokens: int, output_tokens: int, input_per_1k: float, output_per_1k: float) -> float:
    return (input_tokens / 1000.0) * input_per_1k + (output_tokens / 1000.0) * output_per_1k


def make_run_id(dataset_path: Path, config_hash: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{dataset_path.as_posix()}::{config_hash}::{now}"
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"run_{now}_{suffix}"


def percentile(values: List[float], ratio: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def run_eval(dataset_path: Path, config: RunConfig, storage: DevEvalStorage) -> RunResult:
    cases = parse_dataset(dataset_path)
    provider_cfg = ProviderConfig(
        provider=config.provider,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_url=config.api_url,
        api_key=config.api_key,
    )
    provider = build_provider(provider_cfg)

    config_hash = config.hash()
    run_id = make_run_id(dataset_path, config_hash)
    started_at = datetime.now(timezone.utc).isoformat()

    case_results: List[CaseResult] = []

    for case in cases:
        request_payload = {
            "provider": config.provider,
            "model": config.model,
            "prompt_template": config.prompt_template,
            "input": case.input_text,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "api_url": config.api_url,
        }
        cache_key = hashlib.sha256(json.dumps(request_payload, sort_keys=True).encode("utf-8")).hexdigest()
        cached = storage.load_cache(cache_key)

        if cached is not None:
            output = str(cached["output"])
            latency_ms = float(cached["latency_ms"])
            input_tokens = int(cached["input_tokens"])
            output_tokens = int(cached["output_tokens"])
            cache_hit = True
        else:
            full_prompt = f"{config.prompt_template}\n\nUser Input:\n{case.input_text}"
            started = time.perf_counter()
            output = provider.generate(full_prompt)
            elapsed = (time.perf_counter() - started) * 1000.0

            latency_ms = elapsed
            input_tokens = estimate_tokens(full_prompt)
            output_tokens = estimate_tokens(output)
            cache_hit = False

            storage.save_cache(
                cache_key,
                {
                    "output": output,
                    "latency_ms": latency_ms,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

        passed, score = score_case(config.metric, output, case.expected)
        cost_usd = estimate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_per_1k=config.input_cost_per_1k,
            output_per_1k=config.output_cost_per_1k,
        )

        case_results.append(
            CaseResult(
                case_id=case.case_id,
                output=output,
                expected=case.expected,
                passed=passed,
                score=score,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                cache_hit=cache_hit,
            )
        )

    ended_at = datetime.now(timezone.utc).isoformat()

    total = len(case_results)
    passes = sum(1 for c in case_results if c.passed)
    quality = (passes / total) if total else 0.0
    latencies = [c.latency_ms for c in case_results] or [0.0]
    costs = [c.cost_usd for c in case_results] or [0.0]
    cache_hits = sum(1 for c in case_results if c.cache_hit)

    summary = {
        "cases": float(total),
        "pass_count": float(passes),
        "quality": quality,
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": percentile(latencies, 0.95),
        "total_cost_usd": sum(costs),
        "avg_cost_usd": sum(costs) / total if total else 0.0,
        "cache_hit_rate": cache_hits / total if total else 0.0,
    }

    result = RunResult(
        run_id=run_id,
        started_at=started_at,
        ended_at=ended_at,
        dataset_path=dataset_path.as_posix(),
        config_hash=config_hash,
        config={
            "provider": config.provider,
            "model": config.model,
            "prompt_template": config.prompt_template,
            "metric": {"name": config.metric.name, "arg": config.metric.arg},
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "input_cost_per_1k": config.input_cost_per_1k,
            "output_cost_per_1k": config.output_cost_per_1k,
            "api_url": config.api_url,
        },
        summary=summary,
        cases=[c.__dict__ for c in case_results],
    )

    storage.save_run(result.__dict__)
    return result


def diff_runs(base: Dict[str, object], current: Dict[str, object]) -> Dict[str, float]:
    base_summary = base.get("summary", {})
    cur_summary = current.get("summary", {})

    def f(d: Dict[str, object], key: str) -> float:
        v = d.get(key, 0.0)
        if isinstance(v, (int, float)):
            return float(v)
        return 0.0

    return {
        "delta_quality": f(cur_summary, "quality") - f(base_summary, "quality"),
        "delta_latency_p50_ms": f(cur_summary, "latency_p50_ms") - f(base_summary, "latency_p50_ms"),
        "delta_total_cost_usd": f(cur_summary, "total_cost_usd") - f(base_summary, "total_cost_usd"),
        "delta_cache_hit_rate": f(cur_summary, "cache_hit_rate") - f(base_summary, "cache_hit_rate"),
    }
