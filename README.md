# env_law — 환경 법령 리서치 시스템

국가법령정보 공동활용 OpenAPI로 **검증된 근거만** 회신하는 환경 법규 리서치 시스템.
멀티에이전트 자가검증 루프(검색 → 검증 → 평가, 90점 미달 시 최대 4회 재작업)로 LLM의 환각을 차단합니다.

---

## 시작하기 — 3단계

### 1. 법령 API ID(OC) 발급받기 · 무료

이 시스템은 법제처의 국가법령정보 공동활용 OpenAPI를 사용합니다. **본인 ID가 필요합니다.**

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

> `.env` 는 `.gitignore` 에 포함되어 있지만, 공개 전에는 반드시 `git status`와
> 비밀정보 검사를 함께 확인해야 합니다. 파일 권한은 `chmod 600 .env`로 제한하고,
> OC를 이슈·PR·스크린샷·명령 출력에 넣지 마세요.
> 파일을 만들지 않고 `export LAW_API_OC=발급받은ID` 로 한 세션만 쓸 수도 있습니다.

### 3. 설치하고 확인하기

```bash
npm ci                                       # 잠금파일 기준 의존성 설치
./scripts/law_api.sh search law 대기환경보전법   # 동작 확인
```

법령 목록이 JSON으로 출력되면 정상입니다.
ID를 설정하지 않았다면 발급 방법을 안내하는 메시지가 대신 나옵니다.

---

## 사용법

Codex 또는 Claude Code에서 이 폴더를 열고 한국어로 질문하면 동일한 공통 계약으로 리서치 루프를 실행합니다.

- **Codex**: `AGENTS.md`와 `.agents/skills/auto-research-env-law`를 읽고, `.codex/agents`의 검색·검증·평가 역할을 순차 호출합니다. 명시 호출은 `$auto-research-env-law <질의>`입니다.
- **Claude Code**: `CLAUDE.md`와 `.claude/skills/auto-research-env-law`가 같은 공통 계약을 참조합니다.
- **공통 상태**: 새 실행은 `.harness/runs/`에 저장되며 `scripts/harness_state.py`가 단계 순서, JSON 필드, 평가 산술과 OC 마스킹을 검증합니다.

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
| `AGENTS.md` | Codex가 자동으로 읽는 프로젝트 규칙과 검증 명령 |
| `CLAUDE.md` | 지켜야 할 규칙 — 출처 강제, 금칙어, 인용 규격, 시행일 검증 |
| `.agents/skills/auto-research-env-law/` | Codex·Claude 공통 워크플로 및 역할·출력 계약 |
| `.codex/skills/auto-research-env-law` | Codex 설치면에서 공통 스킬을 발견하기 위한 호환 경로 |
| `.codex/agents/` | Codex 네이티브 검색·검증·평가 에이전트 설정 |
| `.claude/skills/` | 리서치 루프 절차서 (반복 횟수·수락 기준) |
| `.claude/agents/` | 검색·검증·평가 담당 에이전트 |
| `scripts/law_api.sh` | 법제처 API 래퍼 (21개 도메인) |
| `scripts/harness_state.py` | 단계 순서·출력 필드·평가 점수·비밀정보를 강제하는 상태 게이트 |
| `scripts/parse_hwp.mjs` | 별표 HWP → HTML 표 변환 (kordoc) |
| `scripts/verify_annex.mjs` | 별표 변환 결과 ↔ 원본 PDF 유사도 검증 |
| `tests/test_harness.py` | 네트워크 없는 Codex 설정·상태·비밀정보 회귀 테스트 (`npm test`) |
| `scripts/test_law_api.sh` | 실제 API 래퍼 회귀 테스트 (`npm run test:api`) |
| `docs/프로젝트_비판적_리뷰.md` | 시스템이 보증하는 범위와 한계 |
| `docs/데이터_출처_및_이용조건.md` | 포함 CSV의 출처 확인·갱신·재배포 시 주의사항 |

## 검증

```bash
npm test              # 오프라인 하네스·보안·상태 계약 테스트
npm run test:api      # 국가법령정보 OpenAPI 라이브 회귀 테스트
npm run test:all      # 오프라인 + 라이브 테스트
./scripts/release_gate.sh              # 깨끗한 작업트리의 공개 배포 게이트
./scripts/release_gate.sh --live       # API + Codex·Claude Code 실제 E2E 포함
```

라이브 테스트는 `.env`의 `LAW_API_OC`와 네트워크가 필요합니다. 기본 `npm test`는 외부 서비스 없이 재현됩니다.
개발 중 미커밋 변경을 진단할 때만 `./scripts/release_gate.sh --allow-dirty`를 사용할 수
있습니다. Gitleaks가 별도 CI에서 실행되는 경우에만 `--skip-gitleaks`를 사용할 수
있으며, 두 옵션 중 하나라도 사용한 결과는 `INCOMPLETE`로 표시되어 공개 배포 승인으로
인정하지 않습니다. `--live`는 모델 호출 비용이 발생하므로 릴리스 담당자가 신뢰된
환경에서 실행합니다.

GitHub Actions의 PR CI는 자격증명 없이 `npm test`와 패키지·의존성 검사를 수행합니다.
라이브 API 검사는 수동 실행 전용이며, 보호된 `live-api` 환경의 `LAW_API_OC` secret이
설정된 경우에만 실행합니다. 외부 포크 PR에는 secret을 제공하지 않습니다.

## 요구 사항

- Node.js 20.9+ · npm 10+ · Python 3.11+ · `curl`
- `pdftotext` (poppler-utils) — 별표 유사도 검증 시에만 필요
- Bash를 제공하는 Linux 또는 macOS. Windows에서는 WSL2의 Ubuntu 등 Bash 환경을
  사용하세요. Windows 네이티브 셸은 현재 지원하지 않습니다.
- Codex CLI(배포 시점의 안정판) 또는 Claude Code 2.1.296+ — 에이전트 워크플로를
  실행할 때만 필요합니다. 기본 API 래퍼와 오프라인 테스트에는 필요하지 않습니다.

## 공개 저장소 보안

- `LAW_API_OC`는 개인별 API 자격증명입니다. `.env` 또는 세션 환경변수에만 보관하고,
  노출되면 즉시 서비스에서 교체한 뒤 모든 기록에서 제거하세요.
- 취약점은 공개 이슈가 아니라 [SECURITY.md](SECURITY.md)의 비공개 신고 절차로
  알려 주세요.
- 코드 기여 절차와 테스트 기준은 [CONTRIBUTING.md](CONTRIBUTING.md)를, 포함 CSV의
  출처·재배포 주의사항은 [데이터 출처 및 이용조건](docs/데이터_출처_및_이용조건.md)을
  참고하세요.

## 한계

이 시스템은 **사람의 최종 검토를 전제로 한 법령 리서치 보조도구**입니다.
인용한 조문이 API 원문에 실제 존재하는지와 시행 중인지는 자동 검증하지만,
그 조문이 해당 시설·규모에 **적용되는지**, 예외·부칙·단서를 누락하지 않았는지는
보증하지 않습니다. 자세한 내용은 `docs/프로젝트_비판적_리뷰.md` 를 참고하세요.
