# 별표 파싱 + 유사도 검증 디자인 (최종)

## 문제 정의

현행 `law_api.sh`의 JSON `별표내용` 필드는 ASCII 박스 문자(│├┤)로 서식된 플레인 텍스트로, 셀 병합이 많은 환경 법령 별표(수질 환경기준 등급표 등)에서 셀 경계가 깨져 법령 해석에 필요한 정확한 값을 추출할 수 없다.

## 실증 결과 요약 (120건, 2026-04-17)
- **kordoc**: 120/120 성공 (100%), HTML 테이블(colspan/rowspan 보존)
- **@rhwp/core**: Node.js 텍스트 추출 불가 (브라우저 전용) → 탈락
- **pdftotext**: 120/120 성공 (100%), 검증용으로 채택
- **평균 유사도**: kordoc↔pdftotext 85.9%, 경고 발생 ~5%

## 최종 전략: kordoc 주 파서 + pdftotext 유사도 검증 + 사용자 알람

| 구성 요소 | 역할 | 기술 스택 |
|---|---|---|
| **korean-law-mcp** | 법령 검색·조회 + kordoc 기반 별표 변환 (주 파서) | TypeScript, kordoc v2.4, MCP 서버 |
| **pdftotext** | 유사도 검증용 2차 소스 | poppler-utils |
| **verify_annex.mjs** | kordoc vs pdftotext 자동 비교 + 경고 수준 판정 | Node.js |
| **사용자 알람** | 유사도 낮을 시 경고 + 원본 링크 제공 | 응답 내 인라인 표시 |

## 파이프라인 흐름

```
[별표 요청]
     │
     ├──────────────┬──────────────────┐
     ▼              ▼                  │
  Lane A         Lane B               │
  kordoc         rhwp                  │
  (MCP tool)     (HWP 다운 → 파싱)     │
     │              │                  │
     ▼              ▼                  │
  MD 테이블 A    MD 테이블 B            │
     │              │                  │
     └──────┬───────┘                  │
            ▼                          │
       [Arbiter]                       │
       정규화 비교                      │
            │                          │
     ┌──────┼──────┐                   │
     ▼      ▼      ▼                   │
  일치    불일치   양쪽실패              │
  A채택   B채택   PDF 폴백 ◄───────────┘
```

## 컴포넌트 상세

### 1. korean-law-mcp MCP 서버

**설치**: `.claude/settings.local.json`에 MCP 서버 등록.

```json
{
  "mcpServers": {
    "korean-law": {
      "command": "npx",
      "args": ["-y", "korean-law-mcp"],
      "env": {
        "LAW_OC": "<발급받은OC>"
      }
    }
  }
}
```

**기존 law_api.sh 대체 매핑**:
- `law_api.sh search <target> <query>` → MCP `search_law` / `search_decisions` 등
- `law_api.sh get <target> <id>` → MCP `get_law_text` / `get_decision_text`
- 별표 추출 → MCP `get_annexes` (kordoc 엔진으로 HWP/HWPX/PDF → 마크다운 변환)

**law_api.sh 유지**: 레거시 호환 및 MCP 서버 장애 시 폴백으로 유지. 별표 파싱만 이중 파서로 대체.

### 2. rhwp 파서

**설치**: `tools/rhwp/`에 소스 클론 후 `cargo build --release`.

**래퍼 스크립트** `scripts/hwp_parse.sh`:
1. API 응답에서 HWP 다운로드 URL 추출 (`별표서식PDF파일링크` 패턴에서 HWP 링크 유도, 또는 `별표HWP파일명`으로 직접 구성)
2. `curl`로 HWP 파일 다운로드 → `/tmp/annex_<id>.hwp`
3. rhwp CLI로 파싱 → JSON 출력 (행/열/셀 값/row_span/col_span)
4. `scripts/hwp_to_md.py`로 JSON → 마크다운 테이블 변환

**hwp_to_md.py 변환 규칙**:
- 병합 셀: 첫 셀에 값 배치, 나머지는 빈칸 (마크다운 표 한계)
- 중첩 표: 외부→내부 순으로 별도 테이블로 분리
- 인코딩: UTF-8 강제

### 3. Arbiter (자동 판정)

**스크립트**: `scripts/annex_arbiter.py`

**입력**: Lane A 마크다운 (kordoc), Lane B 마크다운 (rhwp)

**처리 절차**:
1. 양쪽 마크다운 테이블을 파싱하여 2D 배열로 정규화
   - 공백·개행·특수문자 통일
   - 유니코드 정규화 (NFC)
2. 구조 비교: 행 수, 열 수
3. 셀 값 비교: 정규화 후 문자열 일치율 계산

**판정 기준**:

| 조건 | 판정 | 이유 |
|---|---|---|
| 행×열 동일 + 셀 일치율 ≥ 95% | Lane A(kordoc) 채택 | 경량, 두 엔진이 합의 |
| 행×열 불일치 또는 셀 일치율 < 95% | Lane B(rhwp) 채택 | 구조적 파싱이 더 정확 |
| 양쪽 빈 결과 또는 양쪽 오류 | PDF 폴백 | 3차 소스 |
| Lane A만 성공 | Lane A 채택 (경고 포함) | rhwp 빌드/파싱 실패 |
| Lane B만 성공 | Lane B 채택 (경고 포함) | kordoc 변환 실패 |

**출력**: 판정 결과 JSON + 최종 마크다운 테이블 + diff 로그

**감사 로그**: `.omc/state/annex_audit/<법령ID>_<별표번호>.json`에 저장
```json
{
  "law_id": "283023",
  "annex_no": "0002",
  "lane_a_rows": 15, "lane_a_cols": 3,
  "lane_b_rows": 15, "lane_b_cols": 3,
  "cell_match_rate": 0.97,
  "decision": "lane_a",
  "diffs": [],
  "timestamp": "2026-04-17T..."
}
```

### 4. PDF 폴백

- API 응답의 `별표서식PDF파일링크`에서 PDF 다운로드
- Claude의 Read 도구로 PDF 직접 읽기 (멀티모달)
- 마지막 수단이므로 자동화보다 정확도 우선

## 기존 워크플로우 변경 사항

| 기존 | 변경 후 |
|---|---|
| `law_api.sh search` | korean-law-mcp `search_law` MCP 도구 (law_api.sh는 폴백 유지) |
| `law_api.sh get` | korean-law-mcp `get_law_text` MCP 도구 |
| JSON `별표내용` 직접 파싱 | 병렬 파이프라인 (kordoc + rhwp + Arbiter) |
| `law-researcher.md` — Bash curl 호출 | MCP 도구 호출 + `hwp_parse.sh` 병렬 호출로 전환 |
| `law-verifier.md` — API 재호출 검증 | 동일 유지 + Arbiter 판정 결과 참조 추가 |

## 산출물

| 파일 | 유형 | 설명 |
|---|---|---|
| `.claude/settings.local.json` | 수정 | korean-law-mcp MCP 서버 등록 |
| `tools/rhwp/` | 신규 | rhwp 소스 클론 + 빌드 |
| `scripts/hwp_parse.sh` | 신규 | HWP 다운로드 → rhwp 파싱 → JSON 래퍼 |
| `scripts/hwp_to_md.py` | 신규 | rhwp JSON → 마크다운 테이블 변환 |
| `scripts/annex_arbiter.py` | 신규 | kordoc vs rhwp 자동 비교 판정 |
| `CLAUDE.md` | 수정 | 별표 파싱 파이프라인 규칙 추가 |
| `.claude/agents/law-researcher.md` | 수정 | MCP 도구 + 병렬 파이프라인 호출로 전환 |

## 검증 방법

1. **샘플 별표 3종 변환 테스트**:
   - 단순: 통합법 시행령 별표 1 (통합관리 대상 업종) — 2열
   - 중간: 통합법 시행령 별표 2 (변경허가 대상) — 중첩 호·목
   - 고난이도: 환경정책기본법 시행령 별표 1 수질 환경기준 — 다중 병합셀
2. 각 샘플에 대해 kordoc / rhwp / 원본(PDF 육안) 3-way 비교
3. Arbiter가 올바른 쪽을 채택하는지 확인
4. 기존 질의("통합환경허가 변경허가 기한") 재실행 → 별표 인용 정확도 향상 확인
