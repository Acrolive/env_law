---
name: auto-research-env-law
description: 환경 법령, 환경 고시, 행정규칙, 판례, 자치법규, 통합환경허가, 변경허가, 배출허용기준 질의를 국가법령정보 API로 검색·재검증하고 3개 실무 관점으로 평가한다. 비환경 법률 질의나 단순 용어 설명에는 사용하지 않는다.
---

# 환경 법령 자동 리서치

환경 법규 질의에 대해 검증 가능한 순차 하네스를 실행한다.

## 시작 전에 읽을 파일

1. `references/contract.md`
2. 역할을 직접 수행하거나 해당 에이전트를 호출하기 전에 대응하는 역할 파일:
   - `references/researcher.md`
   - `references/verifier.md`
   - `references/evaluator.md`
3. 별표를 인용할 때 `CLAUDE.md`의 별표 파싱 한계

상대 경로는 이 `SKILL.md`가 있는 디렉터리를 기준으로 해석한다.

## 실행 절차

1. 질의가 시설, 매체, 규모에 따라 결론이 달라지는데 정보가 없으면 한 번에 1~2개만 질문한다.
2. 임시 파일에 질의를 저장하고 다음 명령으로 실행 디렉터리를 만든다.

   `python3 scripts/harness_state.py init --query-file <질의파일>`

3. 최대 4회 반복한다.
   1. `env_law_researcher`를 호출하거나 researcher 역할을 직접 수행한다.
   2. JSON 결과를 임시 파일에 저장하고 `record --stage researcher`로 검증·기록한다.
   3. `env_law_verifier`를 호출하거나 verifier 역할을 직접 수행한다.
   4. JSON 결과를 `record --stage verifier`로 검증·기록한다.
   5. 검증 실패 시 실패 사유를 다음 반복의 `prior_gaps`로 넘기고 평가하지 않는다.
   6. 검증 통과 evidence만 사용해 `CLAUDE.md` 템플릿의 초안을 작성하고 `record --stage draft`로 기록한다.
   7. `env_law_evaluator`를 호출하거나 evaluator 역할을 직접 수행한다.
   8. JSON 결과를 `record --stage evaluation`으로 검증·기록한다.
   9. 평균 90점 이상이면 accepted로 종료한다. 아니면 `must_fix`를 다음 반복의 `prior_gaps`로 넘긴다.
4. 종료 상태를 기록한다.
   - 합격: `python3 scripts/harness_state.py finish --run-dir <경로> --status accepted`
   - 4회 후 미달: `... --status partial`
   - 4회 연속 검증 실패: `... --status failed`
5. `status` 명령으로 상태 계약을 마지막으로 확인한 뒤 응답한다.

## 에이전트 호출 규칙

- 단계는 직전 결과에 의존하므로 병렬로 호출하지 않는다.
- 각 역할에는 원 질의, 현재 반복 번호, 필요한 이전 단계 JSON만 전달한다.
- 역할 에이전트는 상태 파일을 직접 수정하지 않는다. 주 에이전트가 검증 후 기록한다.
- 에이전트 결과가 JSON 계약을 위반하면 의미를 추측해 보정하지 말고 동일 역할에 형식 수정을 요청하거나 직접 다시 작성한다.

## 최종 출력

- 검증 통과 evidence만 인용한다.
- 평가 점수는 정확도 인증이 아니라 내부 체크리스트 충족도로 표시한다.
- 90점 미달이면 점수와 미해결 `must_fix`를 숨기지 않는다.
- 검증 근거가 전혀 없으면 `근거 미확보 — 국가법령정보 API 응답 기준 확답 불가`라고 회신한다.
- 별표가 포함되면 `contract.md`의 경고 수준을 그대로 표시하고 원본 링크를 첨부한다.
