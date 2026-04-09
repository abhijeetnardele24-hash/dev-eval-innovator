from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from deveval.core import parse_metric, score_case


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = REPO_ROOT / "examples" / "support_eval.jsonl"


class CoreMetricTests(unittest.TestCase):
    def test_parse_metric_rejects_unknown_metric(self) -> None:
        with self.assertRaises(ValueError):
            parse_metric("unknown")

    def test_regex_metric_matches_output(self) -> None:
        metric = parse_metric(r"regex:refunds?.*5")
        passed, score = score_case(metric, "Refunds are processed in 5 to 7 business days.", "")
        self.assertTrue(passed)
        self.assertEqual(score, 1.0)


class CliWorkflowTests(unittest.TestCase):
    def run_cli(self, *args: str, workspace: Path | None = None) -> subprocess.CompletedProcess[str]:
        cwd = str(REPO_ROOT)
        if workspace is None:
            workspace = REPO_ROOT
        return subprocess.run(
            [sys.executable, "-m", "deveval", *args, "--workspace", str(workspace)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_run_accepts_workspace_after_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(
                "run",
                "--dataset",
                str(DATASET_PATH),
                "--provider",
                "mock",
                "--model",
                "mock-v1",
                "--prompt-template",
                "You are a helpful support assistant.",
                "--metric",
                "contains:reset",
                workspace=Path(tmp),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("run_id:", result.stdout)

    def test_runs_lists_saved_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            create = self.run_cli(
                "run",
                "--dataset",
                str(DATASET_PATH),
                "--provider",
                "mock",
                "--model",
                "mock-v1",
                "--prompt-template",
                "You are a helpful support assistant.",
                "--metric",
                "contains:reset",
                workspace=workspace,
            )
            self.assertEqual(create.returncode, 0, create.stderr)

            listed = self.run_cli("runs", "--limit", "5", workspace=workspace)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertIn("provider=mock", listed.stdout)

    def test_diff_returns_clean_error_instead_of_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            create = self.run_cli(
                "run",
                "--dataset",
                str(DATASET_PATH),
                "--provider",
                "mock",
                "--model",
                "mock-v1",
                "--prompt-template",
                "You are a helpful support assistant.",
                "--metric",
                "contains:reset",
                "--set-baseline",
                "support_v1",
                workspace=workspace,
            )
            self.assertEqual(create.returncode, 0, create.stderr)

            diff = self.run_cli(
                "diff",
                "--baseline",
                "support_v1",
                "--run-id",
                "missing_run",
                workspace=workspace,
            )
            self.assertEqual(diff.returncode, 2)
            self.assertIn("error: Run not found: missing_run", diff.stderr)

    def test_run_can_fail_on_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = self.run_cli(
                "run",
                "--dataset",
                str(DATASET_PATH),
                "--provider",
                "mock",
                "--model",
                "mock-v1",
                "--prompt-template",
                "You are a helpful support assistant.",
                "--metric",
                "contains:reset",
                "--min-quality",
                "0.9",
                workspace=workspace,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("gate_failed:", result.stderr)

    def test_report_writes_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            created = self.run_cli(
                "run",
                "--dataset",
                str(DATASET_PATH),
                "--provider",
                "mock",
                "--model",
                "mock-v1",
                "--prompt-template",
                "You are a helpful support assistant.",
                "--metric",
                "contains:reset",
                workspace=workspace,
            )
            self.assertEqual(created.returncode, 0, created.stderr)

            run_id = next(
                line.split(": ", 1)[1].strip()
                for line in created.stdout.splitlines()
                if line.startswith("run_id:")
            )
            report_path = workspace / "report.md"

            report = self.run_cli(
                "report",
                "--run-id",
                run_id,
                "--output",
                str(report_path),
                workspace=workspace,
            )
            self.assertEqual(report.returncode, 0, report.stderr)
            self.assertTrue(report_path.exists())
            self.assertIn("# DevEval report:", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
