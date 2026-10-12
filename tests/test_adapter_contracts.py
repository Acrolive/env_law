from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_SKILL = ROOT / ".agents" / "skills" / "auto-research-env-law"
CODEX_SKILL = ROOT / ".codex" / "skills" / "auto-research-env-law"
CLAUDE_SKILL = ROOT / ".claude" / "skills" / "auto-research-env-law" / "SKILL.md"
CLAUDE_VERIFIER = ROOT / ".claude" / "agents" / "law-verifier.md"
CLAUDE_EVALUATOR = ROOT / ".claude" / "agents" / "persona-evaluator.md"


class AdapterContractTests(unittest.TestCase):
    def test_codex_skill_is_a_cross_platform_regular_file_adapter(self) -> None:
        self.assertTrue(COMMON_SKILL.is_dir())
        self.assertTrue(CODEX_SKILL.is_dir())
        self.assertFalse(CODEX_SKILL.is_symlink())

        adapter = CODEX_SKILL / "SKILL.md"
        self.assertTrue(adapter.is_file())
        self.assertFalse(adapter.is_symlink())
        text = adapter.read_text(encoding="utf-8")
        self.assertIn(".agents/skills/auto-research-env-law/SKILL.md", text)
        self.assertIn("references/contract.md", text)
        self.assertIn("references/researcher.md", text)
        self.assertIn("references/verifier.md", text)
        self.assertIn("references/evaluator.md", text)

        agents_md = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("크로스플랫폼 일반 파일 어댑터", agents_md)
        self.assertNotIn("동일 대상 심볼릭 링크", agents_md)

    def test_claude_orchestrator_passes_each_required_stage_input(self) -> None:
        text = CLAUDE_SKILL.read_text(encoding="utf-8")
        self.assertIn("{query, prior_gaps, iteration: iter}", text)
        self.assertIn(
            "{query, iteration: iter, researcher_result: R}",
            text,
        )
        self.assertIn("query, iteration: iter, verified_evidence: V.evidence", text)
        self.assertIn('stage="researcher", iteration=iter', text)
        self.assertIn('stage="verifier", iteration=iter', text)
        self.assertIn('stage="draft", iteration=iter', text)
        self.assertIn('stage="evaluation", iteration=iter', text)
        self.assertIn('status="accepted"', text)
        self.assertIn("harness_state.status(run_dir)", text)

    def test_claude_roles_match_common_json_contract_fields(self) -> None:
        verifier = CLAUDE_VERIFIER.read_text(encoding="utf-8")
        self.assertIn("`iteration`", verifier)
        self.assertIn("`researcher_result`", verifier)
        self.assertIn('"iteration": 1', verifier)
        for field in ('"verified"', '"checked"', '"passed"', '"failed"', '"warnings"', '"evidence"'):
            self.assertIn(field, verifier)

        evaluator = CLAUDE_EVALUATOR.read_text(encoding="utf-8")
        self.assertIn("`iteration`", evaluator)
        self.assertIn('"iteration": 1', evaluator)
        for field in ('"scores"', '"mean"', '"accepted"', '"details"', '"must_fix"'):
            self.assertIn(field, evaluator)

        claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("OC=<OC>", claude_md)
        self.assertNotIn("<발급받은OC>", claude_md)


if __name__ == "__main__":
    unittest.main()
