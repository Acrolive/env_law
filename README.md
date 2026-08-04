# env_law — 환경 법령 리서치 시스템

국가법령정보 공동활용 OpenAPI로 **검증된 근거만** 회신하는 환경 법규 리서치 시스템.
Claude Code와 Codex에서 같은 멀티에이전트 검증 루프(검색 → 검증 → 평가, 90점 미달 시 최대 4회 재작업)를 실행합니다. 이 도구는 사람의 최종 검토를 전제로 하는 법령 리서치 보조도구입니다.

---

## 시작하기 — 3단계

### 1. 법령 API ID(OC) 발급받기 · 무료

이 시스템은 법제처의 국가법령정보 OpenAPI를 사용합니다. **본인 ID가 필요합니다.**

1. https://open.law.go.kr 접속 → 회원가입 → 로그인
2. 상단 **[OPEN API] → [신청]** 에서 이용 신청
3. 발급되는 **"신청자 ID"** 가 OC 값입니다
   - 보통 가입한 이메일의 `@` 앞부분과 같습니다
   - 예: `hong123@gmail.com` 으로 가입 → OC 는 `hong123`

### 2. 발급받은 ID 입력하기

```bash
cp .env.example .env
```

그리고 `.env` 파일을 열어 한 줄만 고치면 됩니다:

```bash
LAW_API_OC=여기에_본인_OC_ID_입력    # ← 이 자리에 발급받은 ID
```

> `.env` 는 `.gitignore` 에 포함되어 있어 실수로 공개될 염려가 없습니다.
> 파일을 만들지 않고 `export LAW_API_OC=발급받은ID` 로 한 세션만 쓸 수도 있습니다.

### 3. 설치하고 확인하기

```bash
npm install                                  # 별표(HWP) 파싱용 kordoc 설치
./scripts/law_api.sh search law 대기환경보전법   # 동작 확인
```

법령 목록이 JSON으로 출력되면 정상입니다.
ID를 설정하지 않았다면 발급 방법을 안내하는 메시지가 대신 나옵니다.

---

## 사용법

Claude Code에서 이 폴더를 열면 `CLAUDE.md`와 `.claude/` 하네스를 사용합니다.
Codex에서 열면 `AGENTS.md`, `.agents/skills/`와 `.codex/agents/` 하네스를 사용합니다.
Codex 조사 역할은 프로젝트 설정과 agent 파일에서 `xhigh` reasoning을 명시합니다.

Codex CLI 재현 실행:

```bash
codex exec --ephemeral -C "$PWD" -s read-only \
  -c 'model_reasoning_effort="xhigh"' \
  '파일 수정 없이 이 프로젝트의 법령 조사 규칙과 최대 반복 횟수를 요약해라.'
```

전체 멀티에이전트 조사는 대화형 세션에서 실행할 수 있습니다. 에이전트 등록 재현은
별도의 라이브 테스트가 새 대화형 PTY 세션에서 실제 자식 세션의
`source.subagent.thread_spawn.agent_role`과 역할별 반환 JSON을 확인합니다.

```bash
codex -C "$PWD" -s workspace-write -a never \
  -c 'model_reasoning_effort="xhigh"'
# 세션 안에서: $auto-research-env-law <환경 법령 질의>
```

프로젝트 hook은 최초 실행 시 Codex의 신뢰 검토가 필요합니다. 대화 기록은
`logs/conversations/`에 저장되며 Git에는 포함되지 않습니다.

API를 직접 쓰려면:

```bash
./scripts/law_api.sh search <target> <검색어>        # 21개 도메인 검색
./scripts/law_api.sh get <target> <MST|ID>          # 전문 조회
./scripts/law_api.sh get-article <target> <MST> <조번호> [시행일]
./scripts/law_api.sh list-annexes <MST>             # 별표 목록
./scripts/law_api.sh get-annex <MST> <별표번호> [hwp|pdf]
node scripts/parse_hwp.mjs <hwp경로>                 # 별표 HWP → HTML 표
```

## 구조

| 경로 | 역할 |
|---|---|
| `CLAUDE.md` | Claude Code 규칙 — 출처 강제, 인용 규격, 시행일 검증 |
| `.claude/skills/` | 리서치 루프 절차서 (반복 횟수·수락 기준) |
| `.claude/agents/` | 검색·검증·평가 담당 에이전트 |
| `AGENTS.md` | Codex가 자동 발견하는 저장소 규칙 |
| `.agents/skills/` | Codex 표준 repo skill |
| `.codex/agents/` | Codex 검색·검증·평가 custom agents |
| `.codex/hooks.json` | Codex 대화 기록 hook |
| `scripts/law_api.sh` | 법제처 API 래퍼 (21개 도메인) |
| `scripts/parse_hwp.mjs` | 별표 HWP → HTML 표 변환 (kordoc) |
| `data/annex_results/` | 별표 파싱 120건 실증 평가 결과 |

## 요구 사항

- Node.js 18+ · Python 3 · `curl`
- `pdftotext` (poppler-utils) — 별표 유사도 검증 시에만 필요

## 검증

```bash
npm test              # 라이브 국가법령정보 API 회귀 테스트
npm run test:harness  # Codex 설정·skill·agent·hook 로거 검증
npm run test:harness:live # 새 Codex 세션에서 세 custom agent 실제 호출 검증
```
