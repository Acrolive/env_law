#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v flock >/dev/null || { echo "FAIL  중복 실행 방지용 flock을 찾을 수 없음"; exit 1; }
command -v pgrep >/dev/null || { echo "FAIL  프로세스 트리 정리용 pgrep을 찾을 수 없음"; exit 1; }

STATE_DIR="${CODEX_HARNESS_STATE_DIR:-$PWD/.harness/state}"
LIVE_TTL="${CODEX_HARNESS_LIVE_TTL:-86400}"
LIVE_FORCE="${CODEX_HARNESS_LIVE_FORCE:-0}"
LIVE_TIMEOUT="${CODEX_HARNESS_LIVE_TIMEOUT:-120}"
[[ "$LIVE_TTL" =~ ^[0-9]+$ ]] || { echo "FAIL  CODEX_HARNESS_LIVE_TTL은 0 이상의 정수여야 함"; exit 2; }
[[ "$LIVE_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo "FAIL  CODEX_HARNESS_LIVE_TIMEOUT은 1 이상의 정수여야 함"; exit 2; }
mkdir -p "$STATE_DIR"

LOCK_FILE="$STATE_DIR/codex-agent-chain-live.lock"
SUCCESS_FILE="$STATE_DIR/codex-agent-chain-live.success"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "SKIP  Codex custom agent live 검증이 이미 실행 중이므로 중복 실행하지 않음"
  exit 0
fi

HARNESS_FILES=(
  AGENTS.md
  .agents/skills/auto-research-env-law/SKILL.md
  .codex/agents/law_researcher.toml
  .codex/agents/law_verifier.toml
  .codex/agents/persona_evaluator.toml
  .codex/config.toml
  scripts/test_codex_agents_live.sh
  scripts/verify_codex_agent_chain.py
)
HARNESS_FINGERPRINT=$(sha256sum "${HARNESS_FILES[@]}" | sha256sum | cut -d' ' -f1)
NOW=$(date +%s)
if [[ "$LIVE_FORCE" != "1" && -s "$SUCCESS_FILE" ]]; then
  read -r LAST_FINGERPRINT LAST_SUCCESS < "$SUCCESS_FILE" || true
  if [[ "$LAST_FINGERPRINT" == "$HARNESS_FINGERPRINT" && "$LAST_SUCCESS" =~ ^[0-9]+$ && $((NOW - LAST_SUCCESS)) -le "$LIVE_TTL" ]]; then
    echo "PASS  변경 없는 Codex custom agent live 검증 결과를 재사용함 (TTL ${LIVE_TTL}초)"
    exit 0
  fi
fi

if [[ "${CODEX_HARNESS_LIVE_DRY_RUN:-0}" == "1" ]]; then
  echo "PASS  Codex custom agent live 가드 dry-run"
  exit 0
fi

command -v codex >/dev/null || { echo "FAIL  codex CLI를 찾을 수 없음"; exit 1; }
command -v script >/dev/null || { echo "FAIL  PTY 실행용 script 명령을 찾을 수 없음"; exit 1; }

TEST_DIR=$(mktemp -d)
RUNNER_PID=""
signal_runner_tree() {
  local signal="$1"
  local current child
  local -a queue descendants children
  queue=("$RUNNER_PID")
  descendants=()

  while ((${#queue[@]})); do
    current="${queue[0]}"
    queue=("${queue[@]:1}")
    mapfile -t children < <(pgrep -P "$current" 2>/dev/null || true)
    for child in "${children[@]}"; do
      [[ -n "$child" ]] || continue
      descendants+=("$child")
      queue+=("$child")
    done
  done

  for ((current=${#descendants[@]} - 1; current >= 0; current--)); do
    kill -"$signal" "${descendants[$current]}" 2>/dev/null || true
  done
  kill -"$signal" "$RUNNER_PID" 2>/dev/null || true
}
terminate_runner() {
  [[ -n "$RUNNER_PID" ]] || return 0
  kill -0 "$RUNNER_PID" 2>/dev/null || { wait "$RUNNER_PID" 2>/dev/null || true; return 0; }

  signal_runner_tree INT
  for _ in $(seq 1 20); do
    kill -0 "$RUNNER_PID" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$RUNNER_PID" 2>/dev/null; then
    signal_runner_tree TERM
    for _ in $(seq 1 20); do
      kill -0 "$RUNNER_PID" 2>/dev/null || break
      sleep 0.1
    done
  fi
  if kill -0 "$RUNNER_PID" 2>/dev/null; then
    signal_runner_tree KILL
  fi
  wait "$RUNNER_PID" 2>/dev/null || true
}
cleanup() {
  terminate_runner
  rm -rf -- "$TEST_DIR"
}
trap cleanup EXIT

if [[ "${CODEX_HARNESS_LIVE_CLEANUP_PROBE:-0}" == "1" ]]; then
  setsid bash -c 'setsid sleep 300 & wait' &
  RUNNER_PID=$!
  sleep 0.1
  mapfile -t PROBE_DESCENDANTS < <(pgrep -P "$RUNNER_PID" 2>/dev/null || true)
  terminate_runner
  PROBE_FAILED=false
  for pid in "$RUNNER_PID" "${PROBE_DESCENDANTS[@]}"; do
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && PROBE_FAILED=true
  done
  RUNNER_PID=""
  [[ "$PROBE_FAILED" == false ]] || { echo "FAIL  Codex live runner 프로세스 트리 정리"; exit 1; }
  echo "PASS  Codex live runner 프로세스 트리 정리"
  exit 0
fi

TRANSCRIPT="$TEST_DIR/codex-tui.log"
START_MARKER="$TEST_DIR/start-marker"
touch "$START_MARKER"

PROMPT='다음 프로젝트 custom agent를 반드시 순서대로 각각 한 번 호출하라: law_researcher, law_verifier, persona_evaluator. 각 spawn은 fork_turns=1로 설정하고 subagent에는 harness_smoke_test=true만 전달한 뒤 완료를 기다려라. fallback, built-in agent 또는 역할극으로 대체하지 마라. 세 호출이 모두 끝난 뒤 HARNESS_AGENT_CHAIN_OK만 출력하라.'

printf -v CODEX_COMMAND '%q ' \
  codex --no-alt-screen --disable hooks \
  -C "$PWD" -s read-only -a never \
  -c 'model_reasoning_effort="xhigh"' \
  "$PROMPT"

setsid script -qefc "$CODEX_COMMAND" "$TRANSCRIPT" >/dev/null 2>&1 &
RUNNER_PID=$!

COMPLETED=false
for _ in $(seq 1 "$LIVE_TIMEOUT"); do
  if python3 scripts/verify_codex_agent_chain.py "$START_MARKER" >/dev/null 2>&1; then
    COMPLETED=true
    break
  fi
  kill -0 "$RUNNER_PID" 2>/dev/null || break
  sleep 1
done

terminate_runner
RUNNER_PID=""

[[ "$COMPLETED" == true ]] || { echo "FAIL  대화형 Codex custom agent 체인 시간 초과"; exit 1; }
python3 scripts/verify_codex_agent_chain.py "$START_MARKER"

SUCCESS_TMP="${SUCCESS_FILE}.tmp.$$"
printf '%s %s\n' "$HARNESS_FINGERPRINT" "$NOW" > "$SUCCESS_TMP"
mv "$SUCCESS_TMP" "$SUCCESS_FILE"

echo "PASS  Codex 대화형 fresh-session custom agent 체인"
