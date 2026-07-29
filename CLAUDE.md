# env_law — 환경 법령 리서치 프로젝트 규칙

## 프로젝트 개요
통합환경관리 대상 사업장의 환경 법규 담당자가 환경 관련 **법령·시행령·시행규칙·행정규칙·판례·자치법규** 에 대해 질의하면, **국가법령정보 공동활용 OpenAPI** (https://www.law.go.kr/DRF) 로 검증된 근거만을 회신한다.

## 사용자 페르소나
- 통합환경허가 대상 사업장의 환경 법규 담당자
- 법령 해석, 적용 근거, 관련 판례, 행정규칙(고시·훈령·예규)을 실무 관점에서 필요로 함
- 잘못된 답변은 곧 행정 리스크 → **환각 0 원칙**

## Hard Rules (위반 금지)
1. **출처 강제**: 국가법령정보 API 응답으로 확인되지 않은 조문·판례·해석을 절대 생성하지 않는다. 확인 불가 시 "근거 미확인 — API 응답 기준 확답 불가" 라고 명시한다.
2. **인용 정확성**: 법령명·조·항·호·공포번호·법령ID·시행일을 그대로 표기한다. 의역하지 않는다 (요약은 별도 섹션에서).
3. **출처 URL 필수**: 모든 인용에 `https://www.law.go.kr/DRF/lawService.do?OC=<발급받은OC>&target=...&ID=...` 형식 또는 법령정보센터 본문 URL을 첨부한다.
4. **금칙어**: "일반적으로", "보통은", "통상" 등 근거 없는 일반화 표현 금지. 대신 구체 조문 인용 또는 "확인 불가" 명시.
5. **개정·시행 상태 검증**: 인용 조문이 시행 중인지(시행일 ≤ 오늘) 확인하고, 시행 전/폐지 조문이면 명시적 경고.

## 자동 워크플로우 (Karpathy Auto-Research)

질의가 들어오면 `auto-research-env-law` 스킬이 다음 루프를 수행한다:

```
prior_gaps = []
for iter in 1..4:
    researcher.run(query, prior_gaps)         # API 검색 + 자기비판
    verified = verifier.run(researcher.out)   # API 재호출 팩트체크
    scores   = evaluator.run(verified)        # 3 페르소나 평가
    if mean(scores) >= 90: break
    prior_gaps = scores.must_fix
render_final(verified, scores)
```

- 4회 이내 90점 미달이면 **솔직히 한계를 보고**하고 부분 결과 + 미해결 사항을 제시한다.

## 응답 템플릿

```markdown
## 질의 요약
<유저 질의 1-2 문장 재구성>

## 결론
<핵심 답변 3-5 문장>

## 근거 법령·행정규칙
- **법령명** (공포번호 제○○○○호, 시행 YYYY-MM-DD)
  - 제○조(제목) 제○항 제○호: "<원문 인용>"
  - 출처: <law.go.kr URL> (법령ID: ○○○○○○)

## 관련 판례
- **○○법원 YYYY-MM-DD 선고 ○○○○도○○○○ 판결**
  - 요지: <판례 요지 원문 일부>
  - 출처: <law.go.kr URL>

## 적용 해석 및 리스크
<사업장 관점 해석, 주의사항, 예외 조항>

## 평가 점수표
| 페르소나 | 점수 | 핵심 코멘트 |
|---|---|---|
| 환경공무원 | NN | ... |
| 환경전문가 | NN | ... |
| 사업장전문가 | NN | ... |
| **평균** | **NN** | (90 이상이어야 최종 출력) |
```

## 별표(첨부 표) 파싱 파이프라인

별표가 포함된 법령 조회 시 다음 파이프라인을 자동으로 수행한다.

### 주 파서: kordoc (npm 직접 호출)
- `node scripts/parse_hwp.mjs <hwp_path>` — kordoc v2.4 npm 패키지를 직접 호출
- HWP/HWPX → HTML 테이블(colspan/rowspan 보존)로 변환
- **120건 실증 테스트에서 100% 파싱 성공** (2026-04-17 검증)
- 외부 MCP 서버 없이 자체 코드만으로 동작 (의존성: kordoc npm만)

### 유사도 검증 (pdftotext 대조)
별표를 인용할 때마다 `scripts/verify_annex.mjs`를 실행하여 kordoc 결과를 pdftotext 결과와 자동 비교한다.

```
kordoc(HWP) ──→ HTML 테이블
pdftotext(PDF) ──→ 레이아웃 텍스트
         │
    유사도 비교 (n-gram)
         │
    ┌────┼────┬────────────┐
    ▼    ▼    ▼            ▼
  ≥70%  50~70%  <50%    파싱실패
  정상   ⚠경고   🚨강한경고  ❌에러
```

### 경고 수준별 대응

| 유사도 | 수준 | 사용자에게 표시 |
|---|---|---|
| ≥ 70% | `ok` | 경고 없이 결과 제공 |
| 50~70% | `warn` | "⚠ 이 별표는 복잡한 표 구조로 변환 정확도가 낮을 수 있습니다. 원본 PDF를 함께 확인하세요." + PDF 다운로드 링크 |
| < 50% | `critical` | "🚨 변환 결과가 원본과 크게 다릅니다. 반드시 원본 확인 필요." + PDF 링크 + HWP 링크 |
| 파싱 실패 | `fail` | "❌ HWP 파싱 실패. 원본 PDF를 직접 확인해 주세요." + PDF 링크 |

### 실증 데이터 (120건, 2026-04-17)
- kordoc 성공률: 100%, pdftotext 성공률: 100%
- 평균 유사도: 85.9%, 경고 발생 예상: ~5% (복잡 병합셀 표)
- 상세: `data/annex_results/evaluation_report.md`

## API 설정
- **CLI 래퍼**: `./scripts/law_api.sh` (자체 코드, curl 기반, 외부 의존 0)
  - `search <target> <query>` — 21개 도메인 검색 (법령·판례·해석례·세무심판 등)
  - `get <target> <MST|ID>` — 법령/행정규칙/판례 전문 조회 (law·englaw는 MST=, admrul·ordin·prec 등은 ID= 파라미터 자동 적용)
  - `get-article <target> <MST|ID> <조번호> [efYd]` — 특정 조항만 조회 (시점별 가능, 행정규칙 조문도 지원)
  - `list-annexes <MST>` — 별표 목록 JSON
  - `get-annex <MST> <별표번호> [hwp|pdf]` — 별표 파일 다운로드
- **별표 변환**: `node scripts/parse_hwp.mjs <hwp_path>` (kordoc npm 직접 호출)
- **유사도 검증**: `node scripts/verify_annex.mjs <hwp_path> <pdf_path>`
- **OC (신청자 ID)**: `.env` 의 `LAW_API_OC` 값 (미설정 시 스크립트가 발급 안내 후 종료). 발급: https://open.law.go.kr — 최초 설정은 README 참조

## 폴더 구조
```
env_law/
├── CLAUDE.md                          # 본 규칙
├── package.json                       # kordoc 의존성 (HWP 파싱용)
├── scripts/
│   ├── law_api.sh                     # 국가법령정보 API curl 래퍼 (21개 도메인)
│   ├── parse_hwp.mjs                  # kordoc 직접 호출 HWP → HTML 변환
│   ├── verify_annex.mjs               # 별표 유사도 검증 스크립트
│   ├── crawl_annexes.py               # 실증 테스트 크롤러
│   ├── run_dual_parse.mjs             # 이중 파서 실행
│   └── compare_results.py             # 3-way 비교 분석
├── data/
│   ├── annex_samples/                 # 실증 테스트 원본 (120건)
│   └── annex_results/                 # 파싱 결과 + 평가 보고서
├── .claude/
│   ├── agents/
│   │   ├── law-researcher.md          # Auto-research 검색 에이전트 (sonnet)
│   │   ├── law-verifier.md            # API 재검증 에이전트 (sonnet)
│   │   └── persona-evaluator.md       # 3 페르소나 평가 에이전트 (sonnet)
│   └── skills/auto-research-env-law/
│       └── SKILL.md                   # 루프 오케스트레이션 스킬
└── .omc/state/                        # 이터레이션 중간 결과
```

## 대화 방식
- **항상 한국어로 응답**
- 질의가 모호하면 (대상 시설/매체/규모 불명확 등) **먼저 1-2개 질문으로 좁힌 후** 검색 시작
- 명확한 질의는 바로 워크플로우 진입
- 사용자가 "근거만", "조문만" 같은 부분 요청 시 평가 단계 생략 가능 (단, API 검증은 생략 불가)
