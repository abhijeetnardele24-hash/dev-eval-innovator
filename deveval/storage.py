from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


class DevEvalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache_dir = self.root / "cache"
        self.runs_dir = self.root / "runs"
        self.baselines_dir = self.root / "baselines"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

    def load_cache(self, cache_key: str) -> Optional[Dict[str, object]]:
        path = self.cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_cache(self, cache_key: str, payload: Dict[str, object]) -> None:
        path = self.cache_dir / f"{cache_key}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def save_run(self, run_payload: Dict[str, object]) -> str:
        run_id = str(run_payload["run_id"])
        path = self.runs_dir / f"{run_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(run_payload, f, indent=2)
        return run_id

    def load_run(self, run_id: str) -> Dict[str, object]:
        path = self.runs_dir / f"{run_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def set_baseline(self, name: str, run_id: str) -> None:
        payload = {"name": name, "run_id": run_id}
        path = self.baselines_dir / f"{name}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def get_baseline_run_id(self, name: str) -> str:
        path = self.baselines_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Baseline not found: {name}")
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        run_id = payload.get("run_id")
        if not run_id:
            raise ValueError(f"Invalid baseline payload for: {name}")
        return str(run_id)

    def list_baselines(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for path in self.baselines_dir.glob("*.json"):
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            out[str(payload.get("name", path.stem))] = str(payload.get("run_id", ""))
        return out

    def list_runs(self) -> List[Dict[str, object]]:
        runs: List[Dict[str, object]] = []
        for path in sorted(self.runs_dir.glob("*.json"), reverse=True):
            with path.open("r", encoding="utf-8") as f:
                runs.append(json.load(f))
        return runs
