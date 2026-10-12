---
name: auto-research-env-law
description: 환경 법령, 환경 고시, 행정규칙, 판례, 자치법규, 통합환경허가, 변경허가, 배출허용기준 질의를 국가법령정보 API로 검색·재검증하고 3개 실무 관점으로 평가한다. 비환경 법률 질의나 단순 용어 설명에는 사용하지 않는다.
---

# 환경 법령 자동 리서치 Codex 어댑터

이 파일은 Windows·macOS·Linux 체크아웃에서 모두 동작하도록 심볼릭 링크 대신 일반 파일로 제공하는 Codex 진입점이다.

실행 전 저장소의 표준 구현인 `.agents/skills/auto-research-env-law/SKILL.md`를 처음부터 끝까지 읽고 그 절차를 그대로 따른다. 이어서 해당 구현이 지정하는 다음 공통 계약·역할 문서를 모두 읽는다.

1. `.agents/skills/auto-research-env-law/references/contract.md`
2. `.agents/skills/auto-research-env-law/references/researcher.md`
3. `.agents/skills/auto-research-env-law/references/verifier.md`
4. `.agents/skills/auto-research-env-law/references/evaluator.md`

`.agents/skills/auto-research-env-law/`가 이 스킬의 단일 규범 원본이다. 이 어댑터와 원본이 충돌하면 원본과 공통 계약을 우선한다. 원본 파일이 없거나 읽을 수 없으면 법령 근거를 추측하지 말고 그 사실을 사용자에게 알린다.
