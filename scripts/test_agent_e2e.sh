#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/load_law_env.sh
. "$ROOT/scripts/load_law_env.sh"
load_law_env "$ROOT/.env"
[[ -n "${LAW_API_OC:-}" ]] || { echo 'LAW_API_OC is not configured' >&2; exit 1; }

command -v codex >/dev/null 2>&1 || { echo 'Codex CLI not found' >&2; exit 1; }
command -v claude >/dev/null 2>&1 || { echo 'Claude Code CLI not found' >&2; exit 1; }

E2E_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/env-law-agent-e2e.XXXXXX")"
trap 'rm -rf -- "$E2E_TMP_DIR"' EXIT

QUERIES=(
  '합성 시험: 대기환경보전법상 배출시설 변경 절차의 법률·시행령·시행규칙·고시 근거를 확인해줘.'
  '합성 시험: 대기환경보전법 시행규칙 별표의 배출시설 항목 하나를 HWP와 PDF 원본으로 대조해 설명해줘.'
  '합성 시험: 국가법령정보 API에서 확인할 수 없는 가상의 환경부 고시를 찾고, 근거가 없으면 근거 미확인으로 종료해줘.'
)

snapshot_manifests() {
  find .harness/runs -type f -name manifest.json -print 2>/dev/null | sort || true
}

output_contains_oc() {
  local output_file="$1"
  printf '%s\n' "$LAW_API_OC" | grep -qF -f - -- "$output_file"
}

report_agent_failure() {
  local output_file="$1"
  if output_contains_oc "$output_file"; then
    echo 'Agent command failed; credential-bearing output was suppressed.' >&2
  else
    tail -n 20 "$output_file" | redact_law_text >&2
  fi
  return 1
}

verify_new_runs() {
  local before_file="$1" after_file="$2" output_file="$3"
  local found=0 manifest run_dir status
  while IFS= read -r manifest; do
    [[ -n "$manifest" ]] || continue
    found=1
    run_dir="$(dirname "$manifest")"
    python3 scripts/harness_state.py validate --run-dir "$run_dir" >/dev/null
    status="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["status"])' "$manifest")"
    [[ "$status" == "accepted" || "$status" == "partial" || "$status" == "failed" ]] || return 1
    if [[ -n "${LAW_API_OC:-}" ]] && \
      printf '%s\n' "$LAW_API_OC" | grep -RIlF -f - -- "$run_dir" >/dev/null; then
      return 1
    fi
  done < <(comm -13 "$before_file" "$after_file")
  ((found == 1)) || return 1
  if output_contains_oc "$output_file"; then
    return 1
  fi
}

run_codex_case() {
  local index="$1" query="$2"
  local before="$E2E_TMP_DIR/codex-${index}.before" after="$E2E_TMP_DIR/codex-${index}.after"
  local output="$E2E_TMP_DIR/codex-${index}.jsonl"
  snapshot_manifests > "$before"
  if ! codex exec --ephemeral --json --sandbox workspace-write --cd "$ROOT" \
    "Use \$auto-research-env-law for this synthetic test question: ${query}" \
    > "$output" 2>&1; then
    report_agent_failure "$output"
    return 1
  fi
  snapshot_manifests > "$after"
  verify_new_runs "$before" "$after" "$output"
}

run_claude_case() {
  local index="$1" query="$2"
  local before="$E2E_TMP_DIR/claude-${index}.before" after="$E2E_TMP_DIR/claude-${index}.after"
  local output="$E2E_TMP_DIR/claude-${index}.jsonl"
  snapshot_manifests > "$before"
  if ! claude --print --no-session-persistence --output-format stream-json --verbose \
    --permission-mode auto --permission-prompts none \
    --max-budget-usd "${CLAUDE_E2E_MAX_BUDGET_USD:-5}" \
    "/auto-research-env-law ${query}" > "$output" 2>&1; then
    report_agent_failure "$output"
    return 1
  fi
  snapshot_manifests > "$after"
  verify_new_runs "$before" "$after" "$output"
}

for index in "${!QUERIES[@]}"; do
  run_codex_case "$index" "${QUERIES[$index]}"
  printf 'PASS  Codex E2E case %s\n' "$((index + 1))"
done

for index in "${!QUERIES[@]}"; do
  run_claude_case "$index" "${QUERIES[$index]}"
  printf 'PASS  Claude Code E2E case %s\n' "$((index + 1))"
done
