# env_law — 환경 법령 리서치 시스템

국가법령정보 공동활용 OpenAPI로 **검증된 근거만** 회신하는 환경 법규 리서치 시스템.
멀티에이전트 자가검증 루프(검색 → 검증 → 평가, 90점 미달 시 최대 4회 재작업)로 LLM의 환각을 차단합니다.

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

Claude Code에서 이 폴더를 열고 한국어로 질문하면, `CLAUDE.md` 의 규칙과
`.claude/skills/auto-research-env-law` 스킬에 따라 자동으로 리서치 루프가 실행됩니다.

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
| `CLAUDE.md` | 지켜야 할 규칙 — 출처 강제, 금칙어, 인용 규격, 시행일 검증 |
| `.claude/skills/` | 리서치 루프 절차서 (반복 횟수·수락 기준) |
| `.claude/agents/` | 검색·검증·평가 담당 에이전트 |
| `scripts/law_api.sh` | 법제처 API 래퍼 (21개 도메인) |
| `scripts/parse_hwp.mjs` | 별표 HWP → HTML 표 변환 (kordoc) |
| `data/annex_results/` | 별표 파싱 120건 실증 평가 결과 |

## 요구 사항

- Node.js 18+ · Python 3 · `curl`
- `pdftotext` (poppler-utils) — 별표 유사도 검증 시에만 필요
