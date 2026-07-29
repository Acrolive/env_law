---
name: conversation-log
description: env_law 프로젝트의 대화 자동 기록 시스템 안내 및 관리. 로그 확인, 특정 날짜 기록 조회, 과거 세션 전체 백필, 기록 시스템 문제 해결 시 사용. 트리거 키워드 "대화 기록", "대화 로그", "conversation log", "기록 확인", "로그 백필".
---

# 대화 자동 기록 (conversation-log)

## 개요

이 프로젝트 폴더에서 이루어지는 **모든 Claude Code 대화(사용자 질문 + Claude 답변)** 는
자동으로 markdown 파일에 기록된다. 별도 조작 없이 매 응답 완료 시점에 동작한다.

## 동작 원리

```
사용자 질문 → Claude 답변 완료
      │
      ▼  Stop hook (.claude/settings.json)
node scripts/log_conversation.mjs
      │  transcript(JSONL)에서 미기록 메시지만 증분 추출
      ▼
logs/conversations/YYYY-MM-DD.md  (일자별 누적)
logs/conversations/.state.json    (세션별 처리 위치 — 중복 기록 방지)
```

- **기록 대상**: 사용자가 직접 입력한 프롬프트, Claude의 최종 텍스트 답변
- **기록 제외**: 도구 호출/결과, thinking, `<system-reminder>` 등 시스템 주입 텍스트
- **파일 단위**: 하루 1개 파일 (`logs/conversations/2026-07-21.md` 형식)
- **엔트리 형식**: `## 🙋 사용자 [HH:MM:SS] (세션 xxxxxxxx)` / `## 🤖 Claude [HH:MM:SS] (세션 xxxxxxxx)`
- 여러 세션이 같은 날 진행되면 세션 ID 앞 8자리로 구분되어 같은 파일에 누적된다.
- 기록 실패 시에도 대화 진행은 절대 차단되지 않는다 (스크립트가 항상 exit 0).

## 사용법

### 오늘 기록 확인
```bash
cat logs/conversations/$(date +%F).md
```

### 특정 날짜 기록 확인
```bash
cat logs/conversations/2026-07-21.md
```

### 기록 전체에서 키워드 검색
```bash
grep -rn "변경허가" logs/conversations/
```

### 과거 세션 전체 백필 (hook 도입 이전 대화 내보내기)
transcript 파일은 `~/.claude/projects/-home-deploy-projects-tablet-projects-env-law/` 아래에
세션 ID 이름의 `.jsonl` 로 저장되어 있다.

```bash
# 세션 목록 확인 (최근 수정 순)
ls -t ~/.claude/projects/-home-deploy-projects-tablet-projects-env-law/*.jsonl | head

# 세션 전체를 markdown 으로 내보내기
node scripts/log_conversation.mjs --full <transcript.jsonl> [출력.md]
# 출력 생략 시 logs/conversations/backfill_<세션8자리>.md 에 저장
```

백필 모드는 상태 파일(`.state.json`)을 건드리지 않으므로 자동 기록과 충돌하지 않는다.

## 문제 해결

1. **기록이 안 될 때**: `.claude/settings.json` 의 `hooks.Stop` 항목 존재 확인 후,
   설정을 이 세션 중에 추가했다면 `/hooks` 를 한 번 열거나 Claude Code 를 재시작해야 반영된다.
2. **수동 테스트**:
   ```bash
   echo '{"session_id":"manualtest","transcript_path":"<transcript.jsonl 경로>"}' \
     | node scripts/log_conversation.mjs
   ```
3. **특정 세션을 처음부터 다시 기록하고 싶을 때**: `logs/conversations/.state.json` 에서
   해당 세션 ID 키를 삭제하면 다음 턴에 전체가 다시 기록된다 (중복 주의 — 백필 모드 권장).

## 주의사항

- 로그에는 대화 원문이 그대로 남는다. 민감 정보를 대화에 입력했다면 해당 날짜 파일에서 직접 삭제할 것.
- transcript 원본은 Claude Code의 `cleanupPeriodDays`(기본 30일) 경과 시 삭제되므로,
  장기 보존이 필요한 기록은 `logs/conversations/` 가 원본 역할을 한다.
