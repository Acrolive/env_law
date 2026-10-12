from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_SCRIPT = ROOT / "scripts" / "harness_state.py"


def run_state(
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(STATE_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
        env=env,
    )


class ProjectSurfaceTests(unittest.TestCase):
    def test_codex_surfaces_are_well_formed(self) -> None:
        agents = sorted((ROOT / ".codex" / "agents").glob("env_law_*.toml"))
        self.assertEqual(len(agents), 3)
        names = set()
        for path in agents:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(data["name"])
            self.assertTrue(data["description"])
            self.assertTrue(data["developer_instructions"])
            self.assertIn("필수 필드", data["developer_instructions"])
            names.add(data["name"])
        self.assertEqual(
            names,
            {"env_law_researcher", "env_law_verifier", "env_law_evaluator"},
        )

        config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertTrue(config["agents"]["enabled"])
        self.assertGreaterEqual(config["agents"]["max_concurrent_threads_per_session"], 3)

    def test_skill_and_project_instructions_reference_shared_contract(self) -> None:
        skill_dir = ROOT / ".agents" / "skills" / "auto-research-env-law"
        compatibility_dir = ROOT / ".codex" / "skills" / "auto-research-env-law"
        self.assertTrue(compatibility_dir.is_dir())
        self.assertFalse(compatibility_dir.is_symlink())
        compatibility_skill = compatibility_dir / "SKILL.md"
        self.assertTrue(compatibility_skill.is_file())
        self.assertIn(
            ".agents/skills/auto-research-env-law/SKILL.md",
            compatibility_skill.read_text(encoding="utf-8"),
        )

        skill = (skill_dir / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(skill.startswith("---\nname: auto-research-env-law\n"))
        self.assertIn("description:", skill)
        self.assertIn("references/contract.md", skill)
        self.assertIn("harness_state.py", skill)

        agents_md = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("$auto-research-env-law", agents_md)
        self.assertIn("env_law_researcher", agents_md)
        self.assertIn("npm test", agents_md)

    def test_law_api_uses_safe_env_loader(self) -> None:
        script = (ROOT / "scripts" / "law_api.sh").read_text(encoding="utf-8")
        self.assertNotIn('. "$_ENV_FILE"', script)
        self.assertIn("load_law_env", script)
        self.assertIn("redact_law_url", script)


class EnvironmentLoaderTests(unittest.TestCase):
    def test_loader_does_not_execute_shell_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            marker = tmp_path / "executed"
            env_file = tmp_path / ".env"
            env_file.write_text(
                "LAW_API_OC=test-user\n"
                f"LAW_API_BASE=$(touch {marker})\n"
                "IGNORED_KEY=value\n",
                encoding="utf-8",
            )
            command = (
                'source scripts/load_law_env.sh; load_law_env "$1"; '
                "printf '%s\\n%s\\n' \"$LAW_API_OC\" \"$LAW_API_BASE\""
            )
            result = subprocess.run(
                ["bash", "-c", command, "--", str(env_file)],
                cwd=ROOT,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith("LAW_API_")
                },
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(result.stdout.splitlines()[0], "test-user")
            self.assertTrue(result.stdout.splitlines()[1].startswith("$(touch "))
            self.assertFalse(marker.exists())

    def test_url_redaction_masks_oc(self) -> None:
        command = (
            "source scripts/load_law_env.sh; "
            "redact_law_url 'https://example.test/api?OC=secret-user&target=law'"
        )
        result = subprocess.run(
            ["bash", "-c", command], cwd=ROOT, text=True, capture_output=True, check=True
        )
        self.assertEqual(
            result.stdout.strip(),
            "https://example.test/api?OC=<redacted>&target=law",
        )


class HarnessStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        query = self.root / "query.txt"
        query.write_text("환경 법령 질의", encoding="utf-8")
        result = run_state(
            "init",
            "--root",
            str(self.root / "runs"),
            "--run-id",
            "test-run",
            "--query-file",
            str(query),
        )
        self.run_dir = Path(result.stdout.strip())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_json(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def record(self, iteration: int, stage: str, input_path: Path, check: bool = True):
        return run_state(
            "record",
            "--run-dir",
            str(self.run_dir),
            "--iteration",
            str(iteration),
            "--stage",
            stage,
            "--input",
            str(input_path),
            check=check,
        )

    def researcher(self, iteration: int = 1) -> dict:
        return {
            "iteration": iteration,
            "queries_executed": ["law:환경"],
            "evidence": {"laws": []},
            "self_critique": {"checklist": {}, "next_queries": []},
            "stop_reason": "sufficient_evidence",
        }

    def verifier(self, iteration: int = 1, verified: bool = True) -> dict:
        failed = [] if verified else [{"reason": "인용 불일치"}]
        return {
            "iteration": iteration,
            "verified": verified,
            "checked": 1,
            "passed": 1 if verified else 0,
            "failed": failed,
            "warnings": [],
            "evidence": {"laws": []},
        }

    def evaluation(self, iteration: int = 1, score: int = 90) -> dict:
        accepted = score >= 90
        return {
            "iteration": iteration,
            "scores": {"official": score, "expert": score, "operator": score},
            "mean": float(score),
            "accepted": accepted,
            "details": [],
            "must_fix": [] if accepted else ["근거 보강"],
        }

    def test_happy_path_and_accepted_finish(self) -> None:
        self.record(1, "researcher", self.write_json("researcher.json", self.researcher()))
        self.record(1, "verifier", self.write_json("verifier.json", self.verifier()))
        draft = self.root / "draft.md"
        draft.write_text("# 검증된 초안\n", encoding="utf-8")
        self.record(1, "draft", draft)
        self.record(1, "evaluation", self.write_json("evaluation.json", self.evaluation()))

        run_state("validate", "--run-dir", str(self.run_dir))
        finish = run_state(
            "finish", "--run-dir", str(self.run_dir), "--status", "accepted"
        )
        self.assertEqual(json.loads(finish.stdout)["status"], "accepted")
        status = json.loads(run_state("status", "--run-dir", str(self.run_dir)).stdout)
        self.assertEqual(status["status"], "accepted")

    def test_stage_order_is_enforced(self) -> None:
        result = self.record(
            1,
            "verifier",
            self.write_json("verifier.json", self.verifier()),
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("researcher", result.stderr)

    def test_evaluation_arithmetic_is_enforced(self) -> None:
        self.record(1, "researcher", self.write_json("researcher.json", self.researcher()))
        self.record(1, "verifier", self.write_json("verifier.json", self.verifier()))
        draft = self.root / "draft.md"
        draft.write_text("초안", encoding="utf-8")
        self.record(1, "draft", draft)
        invalid = self.evaluation(score=80)
        invalid["accepted"] = True
        result = self.record(
            1,
            "evaluation",
            self.write_json("invalid-evaluation.json", invalid),
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("accepted", result.stderr)

    def test_unmasked_oc_is_rejected(self) -> None:
        researcher = self.researcher()
        researcher["evidence"] = {
            "laws": [{"source_url": "https://law.go.kr/DRF/lawService.do?OC=secret&target=law"}]
        }
        result = self.record(
            1,
            "researcher",
            self.write_json("secret.json", researcher),
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("OC", result.stderr)

    def test_configured_oc_in_bare_text_is_rejected(self) -> None:
        researcher = self.researcher()
        researcher["evidence"] = {"note": "credential was plain-test-credential"}
        input_path = self.write_json("bare-secret.json", researcher)
        env = os.environ.copy()
        env["LAW_API_OC"] = "plain-test-credential"
        result = run_state(
            "record",
            "--run-dir",
            str(self.run_dir),
            "--iteration",
            "1",
            "--stage",
            "researcher",
            "--input",
            str(input_path),
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("OC", result.stderr)

    def test_upstream_stage_cannot_be_replaced_after_dependents(self) -> None:
        self.record(1, "researcher", self.write_json("researcher.json", self.researcher()))
        self.record(1, "verifier", self.write_json("verifier.json", self.verifier()))
        replacement = self.researcher()
        replacement["stop_reason"] = "replaced"
        result = run_state(
            "record",
            "--run-dir",
            str(self.run_dir),
            "--iteration",
            "1",
            "--stage",
            "researcher",
            "--input",
            str(self.write_json("replacement.json", replacement)),
            "--replace",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("후속 단계", result.stderr)

    def test_rejected_verifier_blocks_draft_and_evaluation(self) -> None:
        self.record(1, "researcher", self.write_json("researcher.json", self.researcher()))
        self.record(
            1,
            "verifier",
            self.write_json("verifier.json", self.verifier(verified=False)),
        )
        draft = self.root / "draft.md"
        draft.write_text("거부된 근거의 초안", encoding="utf-8")
        result = self.record(1, "draft", draft, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("거부", result.stderr)

    def test_second_iteration_can_be_accepted(self) -> None:
        for iteration, score in ((1, 80), (2, 95)):
            self.record(
                iteration,
                "researcher",
                self.write_json(f"researcher-{iteration}.json", self.researcher(iteration)),
            )
            self.record(
                iteration,
                "verifier",
                self.write_json(f"verifier-{iteration}.json", self.verifier(iteration)),
            )
            draft = self.root / f"draft-{iteration}.md"
            draft.write_text(f"반복 {iteration} 초안", encoding="utf-8")
            self.record(iteration, "draft", draft)
            self.record(
                iteration,
                "evaluation",
                self.write_json(
                    f"evaluation-{iteration}.json",
                    self.evaluation(iteration, score),
                ),
            )
        finish = run_state(
            "finish", "--run-dir", str(self.run_dir), "--status", "accepted"
        )
        self.assertEqual(json.loads(finish.stdout)["status"], "accepted")

    def test_four_low_evaluations_finish_partial(self) -> None:
        for iteration in range(1, 5):
            self.record(
                iteration,
                "researcher",
                self.write_json(f"researcher-{iteration}.json", self.researcher(iteration)),
            )
            self.record(
                iteration,
                "verifier",
                self.write_json(f"verifier-{iteration}.json", self.verifier(iteration)),
            )
            draft = self.root / f"draft-{iteration}.md"
            draft.write_text(f"반복 {iteration} 초안", encoding="utf-8")
            self.record(iteration, "draft", draft)
            self.record(
                iteration,
                "evaluation",
                self.write_json(
                    f"evaluation-{iteration}.json",
                    self.evaluation(iteration, 80),
                ),
            )
        finish = run_state(
            "finish", "--run-dir", str(self.run_dir), "--status", "partial"
        )
        self.assertEqual(json.loads(finish.stdout)["status"], "partial")

    def test_four_verifier_rejections_finish_failed(self) -> None:
        for iteration in range(1, 5):
            self.record(
                iteration,
                "researcher",
                self.write_json(f"researcher-{iteration}.json", self.researcher(iteration)),
            )
            self.record(
                iteration,
                "verifier",
                self.write_json(
                    f"verifier-{iteration}.json",
                    self.verifier(iteration, verified=False),
                ),
            )
        finish = run_state(
            "finish", "--run-dir", str(self.run_dir), "--status", "failed"
        )
        self.assertEqual(json.loads(finish.stdout)["status"], "failed")

    def test_interrupted_run_can_resume(self) -> None:
        self.record(1, "researcher", self.write_json("researcher.json", self.researcher()))
        status = json.loads(run_state("status", "--run-dir", str(self.run_dir)).stdout)
        self.assertEqual(status["status"], "active")
        self.assertEqual(status["current_iteration"], 1)
        self.record(1, "verifier", self.write_json("verifier.json", self.verifier()))
        run_state("validate", "--run-dir", str(self.run_dir))

    def test_manifest_cannot_reference_path_outside_run_directory(self) -> None:
        self.record(1, "researcher", self.write_json("researcher.json", self.researcher()))
        manifest_path = self.run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["stages"]["1"]["researcher"] = "iteration-1/../../outside.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = run_state("validate", "--run-dir", str(self.run_dir), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("벗어난", result.stderr)


if __name__ == "__main__":
    unittest.main()
