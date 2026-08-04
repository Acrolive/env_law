#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PASS=0
check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name"
    exit 1
  fi
}

check "AGENTS.md 크기 제한" bash -c 'test -s AGENTS.md && test "$(wc -c < AGENTS.md)" -lt 32768'
check "Codex skill 발견 경로" test -f .agents/skills/auto-research-env-law/SKILL.md
check "OMX 호환 skill 경로" test -f .codex/skills/auto-research-env-law/SKILL.md
check "Codex 대화 기록 skill" test -f .agents/skills/conversation-log/SKILL.md
check "Codex hooks JSON" python3 -c 'import json; json.load(open(".codex/hooks.json"))'
check "Codex TOML 설정" python3 -c '
import pathlib, tomllib
for path in pathlib.Path(".codex").rglob("*.toml"):
    tomllib.loads(path.read_text())
'
check "Codex agent 계약" python3 -c '
import pathlib, tomllib
agents = list(pathlib.Path(".codex/agents").glob("*.toml"))
assert len(agents) == 3
for path in agents:
    data = tomllib.loads(path.read_text())
    assert all(data.get(key) for key in ("name", "description", "developer_instructions"))
    assert path.stem == data["name"], (path, data["name"])
    assert data.get("model_reasoning_effort") == "xhigh"
'
check "Codex 네트워크 설정" python3 -c '
import tomllib
data = tomllib.load(open(".codex/config.toml", "rb"))
assert data["sandbox_workspace_write"]["network_access"] is True
assert data["features"]["multi_agent"] is True
assert data["agents"]["enabled"] is True
assert data["agents"]["default_subagent_reasoning_effort"] == "xhigh"
'
check "4회/90점 계약" bash -c 'rg -q "최대 4회" AGENTS.md && rg -q "평균 90" AGENTS.md && rg -q "최대 4회" .agents/skills/auto-research-env-law/SKILL.md'
check "Claude/Codex 핵심 계약 동등성" bash -c '
  rg -Fq "law-researcher" CLAUDE.md && rg -Fq "law_researcher" AGENTS.md &&
  rg -Fq "law-verifier" CLAUDE.md && rg -Fq "law_verifier" AGENTS.md &&
  rg -Fq "persona-evaluator" CLAUDE.md && rg -Fq "persona_evaluator" AGENTS.md &&
  rg -Fq "1..4" CLAUDE.md && rg -Fq "최대 4회" AGENTS.md &&
  rg -Fq "mean(scores) >= 90" CLAUDE.md && rg -Fq "평균 90점 이상" AGENTS.md
'
check "Claude/Codex 에이전트 핵심 동작 보존" python3 -c '
import pathlib, tomllib
pairs = {
    "law_researcher": (".claude/agents/law-researcher.md", ["law_api.sh", "get-article", "verify_annex.mjs", "prior_gaps", "source_url"]),
    "law_verifier": (".claude/agents/law-verifier.md", ["law_api.sh", "get-article", "시행", "failed", "evidence"]),
    "persona_evaluator": (".claude/agents/persona-evaluator.md", ["official", "expert", "operator", "accepted", "details", "must_fix"]),
}
for role, (claude_path, tokens) in pairs.items():
    claude = pathlib.Path(claude_path).read_text()
    codex = tomllib.loads(pathlib.Path(f".codex/agents/{role}.toml").read_text())["developer_instructions"]
    for token in tokens:
        assert token in claude, (role, "Claude", token)
        assert token in codex, (role, "Codex", token)
'
check "Codex logger 구문" node --check scripts/log_codex_conversation.mjs
check "Codex live agent 테스트 구문" bash -n scripts/test_codex_agents_live.sh
check "Codex live agent 검증기 구문" python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("scripts/verify_codex_agent_chain.py").read_text())'
check "Codex agent 최소 컨텍스트 계약" bash -c '
  rg -Fq "fork_turns=1" AGENTS.md &&
  rg -Fq "fork_turns=1" .agents/skills/auto-research-env-law/SKILL.md &&
  rg -Fq "research_path" .codex/agents/law_verifier.toml &&
  rg -Fq "verification_path" .codex/agents/persona_evaluator.toml
'
check "Codex 인프라 오류 즉시 중단 계약" bash -c '
  rg -Fq "infrastructure_failure" AGENTS.md &&
  rg -Fq "infrastructure_failure" .agents/skills/auto-research-env-law/SKILL.md &&
  rg -Fq "infrastructure_failure" .codex/agents/law_researcher.toml
'
check "Codex live agent 누수 방지 계약" bash -c '
  rg -Fq "flock -n" scripts/test_codex_agents_live.sh &&
  rg -Fq "CODEX_HARNESS_LIVE_TTL" scripts/test_codex_agents_live.sh &&
  rg -Fq "CODEX_HARNESS_LIVE_FORCE" scripts/test_codex_agents_live.sh &&
  rg -Fq "signal_runner_tree KILL" scripts/test_codex_agents_live.sh &&
  rg -Fq "fork_turns=1" scripts/test_codex_agents_live.sh
'

LIVE_GUARD_DIR=$(mktemp -d)
check "Codex live agent 가드 dry-run" env CODEX_HARNESS_STATE_DIR="$LIVE_GUARD_DIR" CODEX_HARNESS_LIVE_DRY_RUN=1 bash scripts/test_codex_agents_live.sh
check "Codex live runner 프로세스 트리 정리" env CODEX_HARNESS_STATE_DIR="$LIVE_GUARD_DIR" CODEX_HARNESS_LIVE_CLEANUP_PROBE=1 bash scripts/test_codex_agents_live.sh
exec 8>"$LIVE_GUARD_DIR/codex-agent-chain-live.lock"
flock -n 8
check "Codex live agent 동시 실행 차단" bash -c '
  output=$(CODEX_HARNESS_STATE_DIR="$1" CODEX_HARNESS_LIVE_DRY_RUN=1 bash scripts/test_codex_agents_live.sh)
  [[ "$output" == SKIP* ]]
' _ "$LIVE_GUARD_DIR"
exec 8>&-

LIVE_FINGERPRINT=$(sha256sum \
  AGENTS.md \
  .agents/skills/auto-research-env-law/SKILL.md \
  .codex/agents/law_researcher.toml \
  .codex/agents/law_verifier.toml \
  .codex/agents/persona_evaluator.toml \
  .codex/config.toml \
  scripts/test_codex_agents_live.sh \
  scripts/verify_codex_agent_chain.py | sha256sum | cut -d' ' -f1)
printf '%s %s\n' "$LIVE_FINGERPRINT" "$(date +%s)" > "$LIVE_GUARD_DIR/codex-agent-chain-live.success"
check "Codex live agent 성공 결과 재사용" bash -c '
  output=$(CODEX_HARNESS_STATE_DIR="$1" CODEX_HARNESS_LIVE_DRY_RUN=1 bash scripts/test_codex_agents_live.sh)
  [[ "$output" == *"결과를 재사용함"* ]]
' _ "$LIVE_GUARD_DIR"
rm -rf -- "$LIVE_GUARD_DIR"

TEST_DIR=$(mktemp -d)
trap 'rm -rf -- "$TEST_DIR"' EXIT
PROMPT_EVENT='{"hook_event_name":"UserPromptSubmit","session_id":"session-123456","turn_id":"turn-1","prompt":"대기환경보전법 근거를 확인해줘"}'
STOP_EVENT='{"hook_event_name":"Stop","session_id":"session-123456","turn_id":"turn-1","last_assistant_message":"검증된 답변입니다."}'
printf '%s' "$PROMPT_EVENT" | CONVERSATION_LOG_DIR="$TEST_DIR" node scripts/log_codex_conversation.mjs >/dev/null
printf '%s' "$PROMPT_EVENT" | CONVERSATION_LOG_DIR="$TEST_DIR" node scripts/log_codex_conversation.mjs >/dev/null
printf '%s' "$STOP_EVENT" | CONVERSATION_LOG_DIR="$TEST_DIR" node scripts/log_codex_conversation.mjs >/dev/null
LOG_FILE=$(find "$TEST_DIR" -maxdepth 1 -type f -name '*.md' -print -quit)
check "Codex 사용자/답변 로그" bash -c 'rg -q "🙋 사용자" "$1" && rg -q "🤖 Codex" "$1"' _ "$LOG_FILE"
check "Codex hook 중복 방지" bash -c 'test "$(rg -c "codex-event:session-:turn-1:user" "$1")" -eq 1' _ "$LOG_FILE"
check "잘못된 hook 입력 비차단" bash -c 'printf "%s" "{invalid" | CONVERSATION_LOG_DIR="$1" node scripts/log_codex_conversation.mjs >/dev/null' _ "$TEST_DIR"

echo "----------------------------------------"
echo "결과: PASS ${PASS} / FAIL 0"
