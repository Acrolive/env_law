#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v codex >/dev/null || { echo "FAIL  codex CLI를 찾을 수 없음"; exit 1; }
command -v script >/dev/null || { echo "FAIL  PTY 실행용 script 명령을 찾을 수 없음"; exit 1; }

TEST_DIR=$(mktemp -d)
RUNNER_PID=""
cleanup() {
  if [[ -n "$RUNNER_PID" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -INT -- "-$RUNNER_PID" 2>/dev/null || true
  fi
  rm -rf -- "$TEST_DIR"
}
trap cleanup EXIT

TRANSCRIPT="$TEST_DIR/codex-tui.log"
START_MARKER="$TEST_DIR/start-marker"
touch "$START_MARKER"

PROMPT='다음 프로젝트 custom agent를 반드시 순서대로 각각 한 번 호출하라: law_researcher, law_verifier, persona_evaluator. 각 subagent에는 harness_smoke_test=true만 전달하고 완료를 기다려라. fallback, built-in agent 또는 역할극으로 대체하지 마라. 세 호출이 모두 끝난 뒤 HARNESS_AGENT_CHAIN_OK만 출력하라.'

printf -v CODEX_COMMAND '%q ' \
  codex --no-alt-screen --disable hooks \
  -C "$PWD" -s read-only -a never \
  -c 'model_reasoning_effort="xhigh"' \
  "$PROMPT"

setsid script -qefc "$CODEX_COMMAND" "$TRANSCRIPT" >/dev/null 2>&1 &
RUNNER_PID=$!

COMPLETED=false
for _ in $(seq 1 180); do
  if python3 scripts/verify_codex_agent_chain.py "$START_MARKER" >/dev/null 2>&1; then
    COMPLETED=true
    break
  fi
  kill -0 "$RUNNER_PID" 2>/dev/null || break
  sleep 1
done

if kill -0 "$RUNNER_PID" 2>/dev/null; then
  kill -INT -- "-$RUNNER_PID" 2>/dev/null || true
  wait "$RUNNER_PID" 2>/dev/null || true
fi
RUNNER_PID=""

[[ "$COMPLETED" == true ]] || { echo "FAIL  대화형 Codex custom agent 체인 시간 초과"; exit 1; }
python3 scripts/verify_codex_agent_chain.py "$START_MARKER"

echo "PASS  Codex 대화형 fresh-session custom agent 체인"
