#!/usr/bin/env bash
# Safe key-value loader for LAW_API_* settings. This file is sourced by law_api.sh.

load_law_env() {
  local env_file="$1"
  local line key value
  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *"="* ]] || continue

    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^LAW_API_[A-Z0-9_]+$ ]] || continue

    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 ]]; then
      if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]] ||
         [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi

    # Explicit environment variables take precedence over .env values.
    if [[ ! -v "$key" ]]; then
      printf -v "$key" '%s' "$value"
      export "$key"
    fi
  done < "$env_file"
}

redact_law_url() {
  local url="$1"
  printf '%s\n' "$url" | sed -E \
    -e 's/([?&]OC=)[^&[:space:]"<>]+/\1<redacted>/Ig' \
    -e 's/([?&]OC%3[Dd])[^&[:space:]"<>]+/\1<redacted>/Ig'
}

redact_law_text() {
  python3 -c '
import os
import re
import sys

text = sys.stdin.read()
secret = os.environ.get("LAW_API_OC", "")
if secret:
    text = text.replace(secret, "<redacted>")
patterns = (
    r"(?i)([?&]oc(?:=|%3d))([^&\s\"<>]+)",
    r"(?i)(\"?(?:law_api_)?oc\"?\s*[:=]\s*\"?)([^,}\s\"]+)",
)
for pattern in patterns:
    text = re.sub(pattern, lambda match: match.group(1) + "<redacted>", text)
sys.stdout.write(text)
'
}
