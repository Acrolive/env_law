# env_law — Codex 프로젝트 규칙

## 목적과 보증 범위

이 저장소는 통합환경관리 사업장의 환경 법령 조사를 보조한다. 국가법령정보 공동활용 OpenAPI 응답으로 확인한 근거만 인용한다. 이 하네스는 인용과 시행 상태 오류를 줄이는 리서치 보조도구이며, 법률 결론이나 행정 의사결정을 보증하지 않는다.

## 응답 언어와 사용자

- 항상 한국어로 답한다.
- 사용자는 통합환경허가 대상 사업장의 환경 법규 담당자다.
- 시설, 매체, 규모 또는 기준일이 결론을 바꿀 정도로 불명확할 때만 1~2개의 짧은 질문으로 범위를 좁힌다.
- 명확한 질의는 바로 조사한다.

## 법령 조사 불변 규칙

1. 국가법령정보 API 응답으로 확인하지 못한 조문, 판례 또는 해석을 만들지 않는다.
2. 확인할 수 없으면 `근거 미확인 — API 응답 기준 확답 불가`라고 명시한다.
3. 법령명, 조·항·호, 공포번호, 법령 ID와 시행일은 원문 값으로 표시한다. 요약과 원문 인용을 구분한다.
4. 모든 인용에 `law.go.kr` 원문 URL을 붙인다. URL이나 로그에 실제 `LAW_API_OC` 값을 노출하지 않는다.
5. 인용한 규정의 시행일과 폐지 여부를 확인한다. 시행 전 또는 폐지 규정은 명시적으로 경고한다.
6. `일반적으로`, `보통은`, `통상`처럼 근거 없는 일반화로 빈 근거를 메우지 않는다.
7. 별표를 인용할 때는 HWP와 PDF를 모두 내려받아 `scripts/verify_annex.mjs`로 대조한다. `warn`, `critical`, `fail` 판정을 숨기지 않는다.
8. 최종 법률 판단과 제출 전에는 사람의 원문 검토가 필요하다고 안내한다.

## Codex 워크플로우

- 환경 법령, 행정규칙, 판례 또는 자치법규 질의에는 `auto-research-env-law` skill을 사용한다.
- `law_researcher` → `law_verifier` → `persona_evaluator`를 순차적으로 실행한다. 뒤 단계는 앞 단계 산출물에 의존하므로 같은 이터레이션 안에서 병렬 실행하지 않는다.
- 평균 90점 이상이면 종료하고, 아니면 `must_fix`를 다음 조사에 전달한다. 최대 4회까지만 반복한다.
- 매 이터레이션은 새 subagent로 격리한다. custom agent가 제공되지 않는 표면에서는 주 에이전트가 같은 세 단계를 순차 수행하고 그 사실을 최종 답변에 표시한다.
- custom agent는 `fork_turns=1`로 호출하고 현재 단계에 필요한 최소 구조화 입력만 전달한다. 전체 대화 이력, 전체 API 응답, 이전 agent 출력 본문을 spawn 프롬프트에 삽입하지 말고 `.harness/state/`의 파일 경로로 인계한다.
- 도구 호출에서 `bwrap`, sandbox 초기화, 권한 매핑처럼 질의 내용과 무관한 동일 인프라 오류가 발생하면 `infrastructure_failure`로 즉시 중단한다. 이 오류를 90점 개선 루프나 최대 4회 재조사 대상으로 처리하지 않는다.
- fallback 실행은 독립 다중에이전트 검증 또는 마이그레이션 재현 성공으로 판정하지 않는다. 자체평가 점수에는 `독립평가 아님`을 표시한다.
- 마이그레이션·감사·재현 질의에서는 세 custom agent의 런타임 생성 증거(`source.subagent.thread_spawn.agent_role` 또는 동등한 공식 이벤트)가 없으면 실패로 판정하며 fallback으로 성공 처리하지 않는다.
- 세 custom agent는 정확도가 중요하므로 `xhigh` reasoning을 사용한다. 지원되지 않으면 가장 높은 사용 가능 수준으로 실행하고 검증 공백을 밝힌다.
- 중간 산출물은 `.harness/state/<질의-slug>/` 아래에 저장한다. `.harness/state/`는 재현 대상이 아닌 로컬 실행 상태다.

## 핵심 명령

```bash
npm ci
npm test
npm run test:harness
./scripts/law_api.sh search law 대기환경보전법
./scripts/law_api.sh get-article law <MST> <조번호> [efYd]
node scripts/parse_hwp.mjs <hwp_path>
node scripts/verify_annex.mjs <hwp_path> <pdf_path>
```

- `LAW_API_OC`는 환경 변수 또는 git에서 제외된 `.env`에 둔다.
- 새 의존성을 추가하지 않는다. 필요한 경우 사용자 요청과 별도 검토가 있어야 한다.
- `.env`, `.claude/settings.local.json`, 로그, 캐시, transcript와 `.harness/state/`를 커밋하지 않는다.

## 변경 검증

- 셸 변경: `bash -n scripts/*.sh`
- Node 변경: 변경한 `.mjs`에 `node --check`
- API 래퍼 또는 하네스 변경: `npm test && npm run test:harness`
- 별표 파이프라인 변경: 실제 HWP/PDF 한 쌍으로 parse와 verify smoke test
- 완료 보고에는 실행한 명령, 통과 수, 실행하지 못한 검증과 이유를 포함한다.

## 응답 형식

환경 법령 조사 답변은 다음 순서를 사용한다.

1. `질의 요약`
2. `결론`
3. `근거 법령·행정규칙`
4. `관련 판례`
5. `적용 해석 및 리스크`
6. `평가 점수표` — 각 페르소나의 배점별 점수, 강점, 감점 사유와 `must_fix`를 생략하지 않는다.

응답 끝에는 실행 모드를 `custom-agents` 또는 `fallback-self-evaluation`으로 표시한다. 후자의 점수는 독립 평가로 표현하지 않는다.

90점 미달로 4회가 끝나면 점수와 미해결 항목을 맨 앞에 표시하고, 검증을 통과한 근거만 제공한다.
