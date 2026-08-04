---
name: auto-research-env-law
description: 국가법령정보 OpenAPI로 환경 법령·행정규칙·판례·자치법규를 조사하고, 인용 재검증과 3개 실무 관점 평가를 최대 4회 반복해 한국어 답변을 만드는 워크플로우. 환경법, 통합환경허가, 변경허가, 배출허용기준, 대기·수질·폐기물·소음진동·토양 관련 법규 질의에 사용한다.
---

# 환경 법령 자동 리서치

`AGENTS.md`의 법령 조사 불변 규칙을 먼저 적용한다.

## 입력 경계

질의에서 대상 시설, 환경 매체, 규모, 행위, 기준일을 식별한다. 이 중 하나가 달라지면 결론도 달라질 가능성이 큰데 문맥으로 확정할 수 없을 때만 1~2개 질문을 한다. 그 외에는 즉시 조사한다.

## 사전 점검

1. `scripts/law_api.sh`와 필요한 경우 `scripts/parse_hwp.mjs`, `scripts/verify_annex.mjs`가 있는지 확인한다.
2. `LAW_API_OC`가 없으면 발급 절차를 간단히 안내하고 API 근거를 생성하지 않은 채 중단한다. 값 자체는 출력하지 않는다.
3. 질의를 파일명에 안전한 짧은 slug로 바꾸고 `.harness/state/<slug>/`를 사용한다.

## 순차 루프

최대 4회 반복한다. 한 이터레이션의 단계는 서로 의존하므로 병렬 실행하지 않는다.

1. `law_researcher` custom agent를 새 subagent로 실행한다. 입력은 원문 질의, 이터레이션 번호와 `prior_gaps`다.
2. 반환 JSON을 `iter<N>-research.json`에 저장한다.
3. `law_verifier` custom agent를 새 subagent로 실행하고 연구 JSON의 모든 인용을 독립 재호출하게 한다.
4. 반환 JSON을 `iter<N>-verification.json`에 저장한다.
5. 검증 실패가 있으면 실패 사유만 `prior_gaps`로 넘기고 다음 이터레이션으로 간다.
6. 검증된 evidence만 사용해 `AGENTS.md` 응답 순서로 초안을 만든다.
7. `persona_evaluator` custom agent를 새 subagent로 실행한다. 원 질의, 검증된 evidence와 초안을 전달한다.
8. 반환 JSON을 `iter<N>-evaluation.json`에 저장한다.
9. 평균이 90 이상이면 종료한다. 아니면 통합 `must_fix`를 다음 이터레이션의 `prior_gaps`로 넘긴다.

custom agent를 사용할 수 없는 표면에서는 주 에이전트가 같은 역할을 순서대로 수행한다. 검증 재호출과 최대 4회 제한은 생략하지 않는다.

## 별표 처리

별표 수치나 표 구조를 인용할 때 다음을 모두 수행한다.

1. `law_api.sh get-annex`로 HWP와 PDF를 각각 받는다.
2. `parse_hwp.mjs`로 HWP를 변환한다.
3. `verify_annex.mjs`로 PDF와 대조한다.
4. `ok`만 경고 없이 사용한다. `warn`/`critical`은 원본 링크와 경고를 붙이고, `fail`은 변환 본문을 인용하지 않는다.

## 종료와 출력

- 수락: 검증된 답변과 세 페르소나 점수표를 출력한다.
- 4회 후 90점 미달: `⚠ 자체 평가 점수 NN.N (목표 90 미달)`과 `must_fix`를 먼저 표시하고 검증된 부분 결과만 출력한다.
- 4회 연속 검증 실패: `근거 미확인 — API 응답 기준 확답 불가`라고 답하고, 범위를 좁힐 질문 1~2개만 제시한다.
- 사용자가 조문만 요구해도 API 재검증은 유지한다. 페르소나 평가는 생략할 수 있다.
