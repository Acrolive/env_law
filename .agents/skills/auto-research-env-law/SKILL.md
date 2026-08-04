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

1. `law_researcher` custom agent를 `fork_turns=1`인 새 subagent로 실행한다. 입력은 원문 질의, 이터레이션 번호와 `prior_gaps`만 담은 최소 JSON이다.
2. 반환 JSON을 `iter<N>-research.json`에 저장한다.
3. `law_verifier` custom agent를 `fork_turns=1`로 실행한다. spawn 입력에 연구 JSON 본문을 붙이지 말고 `query`, `iteration`, `research_path`만 전달하여 해당 파일의 인용을 독립 재호출하게 한다.
4. 반환 JSON을 `iter<N>-verification.json`에 저장한다.
5. 검증 실패가 있으면 실패 사유만 `prior_gaps`로 넘기고 다음 이터레이션으로 간다.
6. 검증된 evidence만 사용해 `AGENTS.md` 응답 순서로 초안을 만들고 `iter<N>-draft.md`에 저장한다.
7. `persona_evaluator` custom agent를 `fork_turns=1`로 실행한다. spawn 입력에 검증 JSON과 초안 본문을 붙이지 말고 `query`, `iteration`, `verification_path`, `draft_path`만 전달한다.
8. 반환 JSON을 `iter<N>-evaluation.json`에 저장한다.
9. 평균이 90 이상이면 종료한다. 아니면 통합 `must_fix`를 다음 이터레이션의 `prior_gaps`로 넘긴다.

각 agent 산출물의 `agent_role`과 런타임의 생성 증거(`source.subagent.thread_spawn.agent_role` 또는 동등한 공식 이벤트)를 확인한다. 이름만 역할극한 주 에이전트 출력은 custom agent 실행으로 인정하지 않는다.

전체 대화 이력이나 API 전문 응답을 agent 입력으로 복사하지 않는다. agent 간 인계는 위 상태 파일 경로로 한정한다. 도구 호출에서 `bwrap: setting up uid map`, sandbox 초기화 또는 권한 매핑 오류가 한 번이라도 발생하면 결과를 `infrastructure_failure`로 기록하고 즉시 종료한다. 이 오류에는 검증·평가 agent를 호출하지 않으며 4회 루프도 적용하지 않는다.

custom agent를 사용할 수 없는 표면에서는 주 에이전트가 같은 역할을 순서대로 수행한다. 검증 재호출과 최대 4회 제한은 생략하지 않는다. 이때 실행 모드는 `fallback-self-evaluation`이며 점수는 독립 평가가 아니다. 마이그레이션·감사·재현 요청에서는 fallback을 성공으로 판정하지 않고 custom agent 미등록을 실패로 보고한다.

## 별표 처리

별표 수치나 표 구조를 인용할 때 다음을 모두 수행한다.

1. `law_api.sh get-annex`로 HWP와 PDF를 각각 받는다.
2. `parse_hwp.mjs`로 HWP를 변환한다.
3. `verify_annex.mjs`로 PDF와 대조한다.
4. `ok`만 경고 없이 사용한다. `warn`/`critical`은 원본 링크와 경고를 붙이고, `fail`은 변환 본문을 인용하지 않는다.

## 종료와 출력

- 수락: 검증된 답변과 세 페르소나의 배점별 점수, 강점, 감점 사유, `must_fix`를 포함한 상세 점수표를 출력한다.
- 4회 후 90점 미달: `⚠ 자체 평가 점수 NN.N (목표 90 미달)`과 `must_fix`를 먼저 표시하고 검증된 부분 결과만 출력한다.
- 4회 연속 검증 실패: `근거 미확인 — API 응답 기준 확답 불가`라고 답하고, 범위를 좁힐 질문 1~2개만 제시한다.
- 사용자가 조문만 요구해도 API 재검증은 유지한다. 페르소나 평가는 생략할 수 있다.
- 최종 줄에 `실행 모드: custom-agents` 또는 `실행 모드: fallback-self-evaluation (독립평가 아님)`을 표시한다.
