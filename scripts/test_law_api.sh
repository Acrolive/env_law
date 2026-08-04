#!/usr/bin/env bash
# law_api.sh 회귀 테스트 (라이브 API 스모크 테스트)
#
# 실행: npm test  또는  bash scripts/test_law_api.sh
# 요건: .env 의 LAW_API_OC (없으면 law_api.sh 가 안내 후 종료)
# 특성: 국가법령정보 OpenAPI 라이브 호출 (law_api.sh 캐시 사용, TTL 60분)
#
# 케이스 출처: 2026-07-27 ~ 2026-07-31 리서치 세션에서 실제 발견된 결함 3건
#   [BUG-1] get admrul 이 MST= 파라미터로 조회하여 "일치하는 행정규칙이 없습니다" 반환
#   [BUG-2] get-article 이 조문번호가 장(章) 제목과 중복될 때 장 제목(조문여부='전문')을 반환
#   [BUG-3] id_param 이 eflaw(연혁법령)를 ID= 로 오처리하여 조회 실패
# + 핵심 기능 보호 케이스 (검색·조문 추출·별표 목록·에러 경로)

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
API="./scripts/law_api.sh"

PASS=0; FAIL=0
check() {  # check <이름> <파이썬 assert 스크립트>  (stdin으로 API 출력 전달됨)
  local name="$1" script="$2"
  if python3 -c "$script" 2>/dev/null; then
    echo "PASS  $name"; PASS=$((PASS+1))
  else
    echo "FAIL  $name"; FAIL=$((FAIL+1))
  fi
}

# ── [BUG-1 회귀] admrul 은 ID= 파라미터로 조회되어야 함 ─────────────────────
$API get admrul 2100000268396 > /tmp/t_admrul.json 2>/dev/null
check "BUG-1: get admrul → 행정규칙기본정보 반환 (ID= 파라미터 매핑)" "
import json
d=json.load(open('/tmp/t_admrul.json'))
info=d['AdmRulService']['행정규칙기본정보']
assert info.get('행정규칙ID')=='74645', info
assert '업무처리지침' in info.get('행정규칙명','')
"

# ── [BUG-2 회귀] 조문번호가 장 제목과 중복돼도 실제 조문을 반환해야 함 ──────
# 환경오염시설법 제38조: '제6장 벌칙' 장 제목이 조문번호 38을 공유
$API get-article law 287993 38 > /tmp/t_art38.json 2>/dev/null
check "BUG-2a: get-article law 287993 38 → 장 제목이 아닌 벌칙 조문" "
import json
d=json.load(open('/tmp/t_art38.json'))
assert d.get('조문여부')=='조문', d.get('조문여부')
assert '징역' in json.dumps(d,ensure_ascii=False)
"
# 화학물질관리법 제39조: '제5장' 장 제목이 조문번호 39를 공유
$API get-article law 276815 39 > /tmp/t_art39.json 2>/dev/null
check "BUG-2b: get-article law 276815 39 → 사고대비물질 지정 조문" "
import json
d=json.load(open('/tmp/t_art39.json'))
assert d.get('조문여부')=='조문', d.get('조문여부')
assert '사고대비물질' in json.dumps(d,ensure_ascii=False)
"

# ── [BUG-3 회귀] eflaw(연혁법령)는 MST= 파라미터로 조회되어야 함 ────────────
$API get eflaw 276715 20260326 > /tmp/t_eflaw.json 2>/dev/null
check "BUG-3: get eflaw 276715 (efYd 지정) → 연혁본 기본정보 반환 (MST= 매핑 + efYd)" "
import json
d=json.load(open('/tmp/t_eflaw.json'))
b=d['법령']['기본정보']
name=b.get('법령명_한글') or b.get('법령명한글') or ''
assert '대기환경보전법' in name, name
"

# ── 핵심 기능 보호 케이스 ────────────────────────────────────────────────────
$API get-article law 282255 35 > /tmp/t_art35.json 2>/dev/null
check "CORE-1: get-article law (일반 조문) → 연간 보고서 작성 및 제출" "
import json
d=json.load(open('/tmp/t_art35.json'))
assert '연간 보고서' in (d.get('조문제목') or ''), d.get('조문제목')
"

$API get-article admrul 2100000268396 12 > /tmp/t_admart.json 2>/dev/null
check "CORE-2: get-article admrul (행정규칙 조문 추출) → 제12조 연간보고서" "
import json
d=json.load(open('/tmp/t_admart.json'))
txt=d['조문내용'][0]
assert txt.strip().startswith('제12조(') and '연간보고서' in txt
"

$API get-article law 282255 999 > /tmp/t_noart.json 2>/dev/null
check "CORE-3: 존재하지 않는 조문 → error 응답" "
import json
d=json.load(open('/tmp/t_noart.json'))
assert 'error' in d, d
"

$API list-annexes 282255 > /tmp/t_annex.json 2>/dev/null
check "CORE-4: list-annexes → 별표 목록 구조(no/title/hwp 키)" "
import json
bl=json.load(open('/tmp/t_annex.json'))
assert isinstance(bl,list) and len(bl)>0
assert all(k in bl[0] for k in ('no','title','hwp')), bl[0].keys()
"

$API search law "환경오염시설의 통합관리에 관한 법률" 3 > /tmp/t_search.json 2>/dev/null
check "CORE-5: search law → totalCnt ≥ 1" "
import json
d=json.load(open('/tmp/t_search.json'))
assert int(d['LawSearch']['totalCnt'])>=1
"

echo "----------------------------------------"
echo "결과: PASS ${PASS} / FAIL ${FAIL}"
[ "$FAIL" -eq 0 ]
