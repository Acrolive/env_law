# env_law Codex 작업 규칙

## 목적

이 저장소는 환경 법령 질의에 대해 국가법령정보 공동활용 OpenAPI로 확인된 근거만 제공하는 리서치 보조 하네스다. 법률적 결론을 자동 보증하지 않으며 사람의 최종 검토를 전제로 한다.

## 환경 법령 질의 처리

- 환경 법령·행정규칙·판례·자치법규 질의에는 저장소 스킬 `auto-research-env-law`를 사용한다.
- 명시 호출은 `$auto-research-env-law <질의>` 형식이다.
- 공식 저장소 스킬 원본은 `.agents/skills/auto-research-env-law`이며 `.codex/skills/auto-research-env-law/SKILL.md`는 원본을 호출하는 크로스플랫폼 일반 파일 어댑터다.
- 검색, 검증, 초안, 평가는 반드시 순차 실행한다. 이전 단계 결과 없이 다음 단계를 시작하지 않는다.
- Codex 네이티브 에이전트를 사용할 수 있으면 `env_law_researcher`, `env_law_verifier`, `env_law_evaluator`를 이 순서로 사용한다.
- 네이티브 에이전트를 사용할 수 없는 표면에서는 동일 역할과 출력 계약을 주 에이전트가 직접 수행한다.
- 실행 상태는 `python3 scripts/harness_state.py`로 `.harness/runs/`에 기록하고 검증한다. `.omc/state/`는 과거 실행 기록일 뿐 새 실행에 사용하지 않는다.

## 절대 규칙

- API 응답으로 확인하지 않은 조문, 판례, 행정해석을 기억이나 추론으로 보충하지 않는다.
- 확인하지 못한 사항은 `근거 미확인 — API 응답 기준 확답 불가`로 표시한다.
- 인용에는 법령명, 조·항·호, 시행일, 식별자와 출처 URL을 포함한다.
- 시행 전·폐지·연혁 법령은 현행 법령처럼 표현하지 않는다.
- 별표 변환 결과는 원본 PDF와 대조하고, 수치·단위·행·열 관계를 원본 확인 없이 확정하지 않는다.
- `LAW_API_OC` 값을 답변, 로그, 상태 파일, 오류 메시지에 출력하지 않는다.
- `.env`를 셸 코드로 실행하지 않는다.

## 검증 명령

- 기본 오프라인 게이트: `npm test`
- 라이브 국가법령정보 API 게이트: `npm run test:api`
- 전체 게이트: `npm run test:all`
- 하네스 상태 확인: `python3 scripts/harness_state.py status --run-dir <경로>`

## 변경 시 원칙

- 플랫폼 공통 계약은 `.agents/skills/auto-research-env-law/references/`에서 먼저 수정한다.
- `.claude/`와 `.codex/`는 공통 계약을 호출하는 플랫폼 어댑터로 유지한다.
- 출력 필드를 변경하면 `scripts/harness_state.py`와 `tests/test_harness.py`를 함께 갱신한다.
- 외부 의존성을 추가하지 않는다.
