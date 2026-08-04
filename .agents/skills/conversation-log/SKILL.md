---
name: conversation-log
description: env_law의 Codex 대화 기록 hook을 확인·테스트·문제 해결하거나 날짜별 로컬 대화 로그를 조회할 때 사용한다.
---

# Codex 대화 기록

## 구조

`.codex/hooks.json`이 두 안정 이벤트를 `scripts/log_codex_conversation.mjs`로 전달한다.

- `UserPromptSubmit.prompt` → 사용자 메시지
- `Stop.last_assistant_message` → Codex 최종 메시지
- 출력 → `logs/conversations/YYYY-MM-DD.md`

Codex의 `transcript_path` 형식은 안정 계약이 아니므로 transcript를 파싱하지 않는다. 세션·턴·역할 marker로 같은 hook 이벤트의 중복 기록을 막는다. 로그 실패는 대화를 중단시키지 않는다.

## 사용법

```bash
cat logs/conversations/$(date +%F).md
rg "변경허가" logs/conversations/
npm run test:harness
```

## 문제 해결

1. 프로젝트를 신뢰한 상태인지 확인한다.
2. Codex CLI의 `/hooks`에서 `.codex/hooks.json`의 현재 hash를 검토하고 신뢰한다. hook 파일이 바뀌면 다시 검토한다.
3. `npm run test:harness`로 fixture 기반 기록과 중복 방지를 검사한다.
4. 실제 로그는 git에서 제외되며 민감정보가 포함된 항목은 로컬 파일에서 제거한다.

자동화가 hook 내용을 사전에 검토한 경우에만 `--dangerously-bypass-hook-trust`를 사용한다. 일상 실행에서 이 옵션을 기본값으로 두지 않는다.
