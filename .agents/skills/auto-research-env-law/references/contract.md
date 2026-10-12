# 플랫폼 공통 하네스 계약

## 보증 범위

이 하네스는 인용 문자열의 API 원문 존재 여부, 출처 형식, 시행 상태와 일부 별표 변환 품질을 점검한다. 해당 조문이 특정 시설·규모에 적용되는지, 예외·부칙이 완전한지, 법률적 결론이 옳은지는 자동 보증하지 않는다.

## 실행 상태

- 최대 반복: 4
- 수락 기준: 3개 페르소나 평균 90점 이상
- 실행 디렉터리: `.harness/runs/<run-id>/`
- 단계 순서: `researcher → verifier → draft → evaluation`
- verifier가 거부하면 같은 반복의 draft와 evaluation은 만들지 않는다.
- 상태 기록은 `scripts/harness_state.py`를 통과해야 한다.

## Researcher JSON 필수 필드

```json
{
  "iteration": 1,
  "queries_executed": [],
  "evidence": {"laws": [], "admrul": [], "precedents": [], "ordin": [], "annexes": []},
  "self_critique": {"checklist": {}, "next_queries": []},
  "stop_reason": "sufficient_evidence"
}
```

각 evidence 항목은 가능한 경우 식별자, 이름, 시행일·상태, 원문 인용, source URL을 포함한다. 빈 본문이나 미확인 값은 추측하지 않고 `null` 또는 빈 배열로 둔다.

## Verifier JSON 필수 필드

```json
{
  "iteration": 1,
  "verified": true,
  "checked": 1,
  "passed": 1,
  "failed": [],
  "warnings": [],
  "evidence": {}
}
```

`verified`는 `failed`가 비어 있을 때만 true다. `evidence`에는 통과한 항목만 남긴다.

## Evaluator JSON 필수 필드

```json
{
  "iteration": 1,
  "scores": {"official": 90, "expert": 90, "operator": 90},
  "mean": 90.0,
  "accepted": true,
  "details": [],
  "must_fix": []
}
```

`mean`은 세 점수의 산술평균이고 `accepted`는 `mean >= 90`과 정확히 일치해야 한다.

## 별표 검증 수준

- `ok`: 유사도 70% 이상. 그래도 원본 PDF 링크를 제공한다.
- `warn`: 50% 이상 70% 미만. 변환 정확도 경고와 PDF 링크를 제공한다.
- `critical`: 50% 미만. 강한 경고와 PDF/HWP 링크를 제공한다.
- `fail`: 변환 내용을 인용하지 않고 원본 링크만 제공한다.

텍스트 유사도는 행·열, 수치·단위, 부등호, 각주의 의미 보존을 증명하지 않는다.

## 비밀정보

- `LAW_API_OC`는 API 요청에만 사용한다.
- 상태 JSON, 초안, 최종 응답, URL 예시와 오류 로그에는 실제 값을 기록하지 않는다.
- 공유 URL은 OC를 제거하거나 `<OC>`로 치환한다.
