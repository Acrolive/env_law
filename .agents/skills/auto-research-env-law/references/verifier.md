# Verifier 역할

## 입력

- 원 질의
- 반복 번호
- researcher JSON

## 절차

1. 모든 evidence를 `scripts/law_api.sh`로 독립 재호출한다.
2. 공백을 정규화한 뒤 인용 문자열이 API 본문에 부분 문자열로 존재하는지 확인한다.
3. 시행일을 현재 날짜와 비교하고 폐지·시행 전·연혁 상태를 표시한다.
4. 출처 URL의 target과 식별자가 evidence와 일치하는지 확인한다. OC 값 자체는 검증·출력하지 않는다.
5. 별표 인용에는 `verify_annex.mjs`의 수준과 원본 링크가 있는지 확인한다.
6. 실패한 항목은 통과 evidence에서 제거한다. 인용을 임의로 보정하지 않는다.

## 출력

`contract.md`의 Verifier JSON 하나만 반환한다. 설명용 Markdown을 붙이지 않는다. 실패 사유는 다음 반복이 바로 실행할 수 있을 만큼 구체적으로 작성한다.
