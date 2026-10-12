#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_LIVE_API=0
RUN_AGENT_E2E=0
ALLOW_DIRTY=0
SKIP_GITLEAKS=0
INCOMPLETE=0

usage() {
  cat <<'EOF'
Usage: scripts/release_gate.sh [--live | --live-api-only] [--allow-dirty] [--skip-gitleaks]

  (no option)      Offline public-release checks
  --live           Offline checks + live API + Codex/Claude E2E
  --live-api-only  Offline checks + live API (trusted CI environment)
  --allow-dirty    Development diagnostics only; never a release approval
  --skip-gitleaks  Split-CI diagnostics only; result is INCOMPLETE, not approval
EOF
}

while (($#)); do
  case "$1" in
    --live) RUN_LIVE_API=1; RUN_AGENT_E2E=1 ;;
    --live-api-only) RUN_LIVE_API=1 ;;
    --allow-dirty) ALLOW_DIRTY=1; INCOMPLETE=1 ;;
    --skip-gitleaks) SKIP_GITLEAKS=1; INCOMPLETE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

if ((RUN_LIVE_API)); then
  # shellcheck source=scripts/load_law_env.sh
  . "$ROOT/scripts/load_law_env.sh"
  load_law_env "$ROOT/.env"
fi

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1" >&2; exit 1; }
run_step() {
  local label="$1"
  shift
  if "$@"; then
    pass "$label"
  else
    fail "$label"
  fi
}

check_git_state() {
  if ((ALLOW_DIRTY)); then
    printf 'WARN  Git worktree cleanliness skipped by --allow-dirty\n'
    return 0
  fi
  [[ -z "$(git status --porcelain=v1 --untracked-files=all)" ]]
}

check_forbidden_tracked_files() {
  local tracked
  tracked="$(git ls-files)"
  ! grep -E '(^|/)(\.env|\.harness|\.omc|\.omx|node_modules)(/|$)|(^|/).*\.(log|jsonl)$' <<< "$tracked" \
    | grep -vE '(^|/)\.env\.example$' >/dev/null
}

check_current_oc() {
  [[ -n "${LAW_API_OC:-}" ]] || return 0
  local path
  while IFS= read -r -d '' path; do
    if printf '%s\n' "$LAW_API_OC" | grep -IqF -f - -- "$path"; then
      return 1
    fi
  done < <(
    find . \
      ! -path './.git/*' \
      ! -path './node_modules/*' \
      ! -path './.env' \
      -type f -print0
  )
  if printf '%s\n' "$LAW_API_OC" | git grep -qF -f - -- .; then
    return 1
  fi
  while IFS= read -r commit; do
    if printf '%s\n' "$LAW_API_OC" | git grep -qF -f - "$commit" -- . 2>/dev/null; then
      return 1
    fi
  done < <(git rev-list --all)
}

check_syntax() {
  while IFS= read -r -d '' script; do
    bash -n "$script"
  done < <(find scripts -type f -name '*.sh' -print0)
  python3 -m compileall -q scripts tests
  while IFS= read -r -d '' script; do
    node --check "$script"
  done < <(find scripts -type f \( -name '*.js' -o -name '*.mjs' \) -print0)
}

check_pack() {
  local result_file
  result_file="$(mktemp "${TMPDIR:-/tmp}/env-law-pack.XXXXXX")"
  if ! npm pack --dry-run --json > "$result_file"; then
    rm -f -- "$result_file"
    return 1
  fi
  if ! node - "$result_file" <<'NODE'
const fs = require('node:fs');
const [{ files = [] }] = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const prohibited = (path) =>
  (path !== '.env.example' && /^\.env(?:\.|$)/.test(path)) ||
  /(^|\/)(\.omc\/|\.omx\/|\.harness\/|node_modules\/|.*\.(?:log|jsonl)$)/.test(path);
const found = files.map(({ path }) => path).filter(prohibited);
if (found.length) process.exit(1);
NODE
  then
    rm -f -- "$result_file"
    return 1
  fi
  rm -f -- "$result_file"
}

check_env_mode() {
  [[ ! -f .env ]] && return 0
  python3 - .env <<'PY'
import os
import stat
import sys

mode = stat.S_IMODE(os.stat(sys.argv[1]).st_mode)
raise SystemExit(0 if mode == 0o600 else 1)
PY
}

check_gitleaks_tree() {
  local scan_dir
  scan_dir="$(mktemp -d "${TMPDIR:-/tmp}/env-law-gitleaks.XXXXXX")"
  if ! git ls-files --cached --others --exclude-standard -z \
    | tar --null -T - -cf - \
    | tar -xf - -C "$scan_dir"; then
    rm -rf -- "$scan_dir"
    return 1
  fi
  if ! gitleaks dir "$scan_dir" --config "$ROOT/.gitleaks.toml" --redact --no-banner; then
    rm -rf -- "$scan_dir"
    return 1
  fi
  rm -rf -- "$scan_dir"
}

run_step "Git worktree state" check_git_state
run_step "Forbidden tracked paths" check_forbidden_tracked_files
run_step "Current OC absent from files and history" check_current_oc
run_step "Shell, Python and Node syntax" check_syntax
run_step "Offline unit and contract tests" npm test
run_step "Production dependency audit" npm audit --omit=dev --audit-level=low
run_step "Package excludes runtime state" check_pack

if ((SKIP_GITLEAKS)); then
  printf 'WARN  Gitleaks skipped; this result is not a release approval\n'
elif command -v gitleaks >/dev/null 2>&1; then
  run_step "Gitleaks repository history" gitleaks git --config "$ROOT/.gitleaks.toml" --redact --no-banner
  run_step "Gitleaks public working tree" check_gitleaks_tree
else
  fail "gitleaks is required; install it or use --skip-gitleaks for incomplete diagnostics"
fi

if ((RUN_LIVE_API)); then
  [[ -n "${LAW_API_OC:-}" || -f .env ]] || fail "LAW_API_OC is not configured"
  run_step ".env permission" check_env_mode
  run_step "Live API regression tests" npm run test:api
fi

if ((RUN_AGENT_E2E)); then
  run_step "Codex and Claude Code E2E" bash scripts/test_agent_e2e.sh
fi

if ((INCOMPLETE)); then
  printf 'RELEASE_GATE=INCOMPLETE\n'
else
  printf 'RELEASE_GATE=PASS\n'
fi
