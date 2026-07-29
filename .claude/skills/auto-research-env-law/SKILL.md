---
name: auto-research-env-law
description: 환경 법령·행정규칙·판례·자치법규 질의가 들어왔을 때 law-researcher → law-verifier → persona-evaluator 루프를 4회까지 돌려 검증된 답변을 만드는 오케스트레이션 스킬. 트리거 키워드 "통합환경", "통합환경허가", "변경허가", "배출허용기준", "대기환경보전법", "물환경보전법", "폐기물관리법", "환경영향평가법", "소음진동", "토양환경", "환경법", "환경 법령", "환경 고시", "환경 판례", "환경 행정규칙" 등 환경 법규 관련 질의 일반.
---

# auto-research-env-law

환경 법규 질의에 대해 **국가법령정보 OpenAPI 기반 Karpathy auto-research 루프**를 수행한다.

## 사전 조건
- `scripts/law_api.sh` 실행 가능 (chmod +x, 21개 도메인 지원)
- `node scripts/parse_hwp.mjs` 실행 가능 (kordoc npm 설치: `npm install kordoc`)
- `node scripts/verify_annex.mjs` 실행 가능 (별표 유사도 검증)
- `pdftotext` 설치 (poppler-utils)
- 외부 MCP 서버 불필요 — 자체 코드만으로 동작

## 루프

```
prior_gaps = []
final = null

for iter in 1..4:
    # 1) 검색 (Karpathy auto-research, MCP 도구 + kordoc)
    R = Agent(law-researcher, {query, prior_gaps, iteration: iter})
    # → 별표 인용 시 verify_annex.mjs 자동 실행, 경고 수준 포함

    # 2) 검증 (API 재호출 팩트체크 + 별표 유사도 확인)
    V = Agent(law-verifier, {evidence: R.evidence})

    if not V.verified:
        prior_gaps = [f.reason for f in V.failed]
        continue   # 인용 자체가 틀렸으므로 평가 의미 없음

    # 3) 답변 초안 작성 (CLAUDE.md 응답 템플릿)
    draft = render_template(query, V.evidence)

    # 4) 평가 (3 페르소나)
    E = Agent(persona-evaluator, {query, verified_evidence: V.evidence, draft_answer: draft})

    if E.accepted:   # mean >= 90
        final = (draft, E)
        break
    else:
        prior_gaps = E.must_fix

if final is None:
    emit_partial_with_caveat(last_draft, last_E.scores, last_E.must_fix)
else:
    emit(final.draft + score_table(final.E.scores))
```

## 에이전트 호출 규칙
- 매 이터레이션 새 sub-agent (`Agent` tool) 로 디스패치 → 컨텍스트 격리
- 중간 결과는 `.omc/state/` 에 `Write` 도구로 파일 적재 (세션 추적; OMC 플러그인은 본 프로젝트에서 비활성화되어 있으므로 state_write MCP 도구를 사용하지 않는다)
- 병렬화 금지 (각 단계가 직전 단계에 의존)

## 부분 결과 처리 (4회 후 90점 미달)
- 전체 답변에 다음 헤더 추가:
  ```
  ⚠ 자체 평가 점수 NN.N (목표 90 미달). 아래 미해결 항목 있음:
  - <must_fix 1>
  - <must_fix 2>
  ```
- 그래도 검증된 evidence 만 인용

## 완전 실패 처리 (verifier 가 4회 연속 reject)
- "근거 미확보 — 국가법령정보 API 응답 기준 확답 불가" 로 회신
- 사용자 질의를 구체화할 수 있는 1-2개 follow-up 질문 제시

## 트리거하지 않는 경우
- 단순 한국어 잡담
- 비-환경 분야 법령 (민사·형사 일반)
- API 호출 없이 답할 수 있는 정의·용어 설명만 필요한 경우 (단, 사용자가 명시 요청한 경우에만)

## 별표 경고 표시
최종 응답에서 별표를 인용한 경우, verify_annex.mjs 의 판정 결과에 따라 경고를 표시한다:
- `level: ok` → 경고 없음
- `level: warn` → 별표 인용 아래에 "⚠ 이 별표는 복잡한 표 구조로 변환 정확도가 낮을 수 있습니다. [원본 PDF 확인](URL)" 표시
- `level: critical` → "🚨 변환 결과가 원본과 크게 다릅니다. [반드시 원본 확인](URL)" 표시
- `level: fail` → 별표 본문 대신 "❌ HWP 파싱 실패. [원본 PDF 직접 확인](URL)" 으로 대체

## 스킬 출력
CLAUDE.md "응답 템플릿" 섹션 양식 그대로 + 평가 점수표 + 별표 검증 경고(해당 시).
