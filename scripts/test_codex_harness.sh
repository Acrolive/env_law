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
    assert "model" not in data and "model_reasoning_effort" not in data
'
check "Codex 네트워크 설정" python3 -c '
import tomllib
data = tomllib.load(open(".codex/config.toml", "rb"))
assert data["sandbox_workspace_write"]["network_access"] is True
'
check "4회/90점 계약" bash -c 'rg -q "최대 4회" AGENTS.md && rg -q "평균 90" AGENTS.md && rg -q "최대 4회" .agents/skills/auto-research-env-law/SKILL.md'
check "Codex logger 구문" node --check scripts/log_codex_conversation.mjs

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
