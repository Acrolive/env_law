#!/usr/bin/env bash
# 국가법령정보 공동활용 OpenAPI curl 래퍼 (고도화)
#
# Usage:
#   law_api.sh search       <target> <query> [display=20]
#   law_api.sh get          <target> <MST|ID> [efYd]
#   law_api.sh get-article  <target> <MST|ID> <조번호> [efYd=YYYYMMDD]
#   law_api.sh list-annexes <MST>
#   law_api.sh get-annex    <MST> <별표번호> [format=hwp|pdf] [outdir=/tmp]
#
# target (검색):
#   법령계: law, admrul, ordin
#   판례계: prec, detc, expc, taxp, nilt, ftcr, pipc, admr, acrc
#           labc, appeal, acrs, educ, pcorp, pinst, trty, englaw
#
# 본문 조회(get/get-article) 파라미터:
#   law, eflaw, englaw   → MST= (법령 마스터번호; eflaw는 efYd 필수)
#   admrul, ordin, prec 등 그 외 → ID= (일련번호)
#   ※ admrul을 MST=로 조회하면 "일치하는 행정규칙이 없습니다" 오류 반환 (2026-07-27 확인)
#
# env: LAW_API_OC (필수) — https://open.law.go.kr 에서 발급

set -euo pipefail
umask 077

# .env 자동 로드 (프로젝트 루트). 설정 파일을 셸 코드로 실행하지 않는다.
_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_ENV_FILE="${_PROJECT_ROOT}/.env"
# shellcheck source=scripts/load_law_env.sh
. "${_PROJECT_ROOT}/scripts/load_law_env.sh"
load_law_env "$_ENV_FILE"

OC="${LAW_API_OC:-}"
if [ -z "$OC" ]; then
  cat >&2 <<'EOF'
[설정 필요] 국가법령정보 OpenAPI 신청자 ID(OC)가 없습니다.

  1) https://open.law.go.kr 에서 무료 신청 (본인 이메일 ID 앞부분이 OC 값)
  2) 아래 중 하나로 설정:

     export LAW_API_OC="발급받은ID"          # 이번 세션만
     echo 'LAW_API_OC=발급받은ID' > .env       # 프로젝트에 저장 (권장)

EOF
  exit 3
fi
BASE="${LAW_API_BASE:-https://www.law.go.kr/DRF}"
DL_BASE="https://www.law.go.kr"
ENCODED_OC="$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1], safe=""))' "$OC")"

# 응답 캐시: 같은 질의 내에서 researcher/verifier/get-annex 가 동일 전문을
# 반복 조회하는 것을 방지. 캐시 내용은 API 응답 원문 그대로이므로 검증 원칙 유지.
CACHE_DIR="${LAW_API_CACHE_DIR:-${TMPDIR:-/tmp}/env_law-api-${UID}}"
CACHE_TTL_MIN="${LAW_API_CACHE_TTL_MIN:-60}"
CURL_OPTS=(-sS --max-time "${LAW_API_TIMEOUT:-30}" --retry 2 --retry-delay 1)

usage() {
  cat >&2 <<'EOF'
Usage:
  law_api.sh search       <target> <query> [display=20]
  law_api.sh get          <target> <MST|ID> [efYd]
  law_api.sh get-article  <target> <MST|ID> <조번호> [efYd]
  law_api.sh list-annexes <MST>
  law_api.sh get-annex    <MST> <별표번호> [format=hwp|pdf] [outdir=/tmp]

식별자: law/eflaw/englaw 는 MST(마스터번호, eflaw는 efYd 필수), admrul/ordin/prec 등은 ID(일련번호) 자동 적용

target (search/get):
  법령: law, admrul, ordin
  판례: prec    (대법원)       detc  (헌법재판소)
        expc    (해석례)       taxp  (세무심판)
        nilt    (노동위원회)   ftcr  (공정거래위)
        pipc    (개인정보위)   admr  (행정심판)
        acrc    (국민권익위)   labc  (노동심판)
        appeal  (항고심)       acrs  (국민권익특별)
        educ    (학교분쟁)     pcorp (공공기관)
        pinst   (공공기관2)    trty  (조약)
        englaw  (영문법령)

env: LAW_API_OC (필수) — https://open.law.go.kr 에서 발급
EOF
  exit 2
}

urlencode() {
  python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

die_input() {
  printf 'law_api: invalid %s\n' "$1" >&2
  exit 2
}

validate_target() {
  case "$1" in
    law|eflaw|admrul|ordin|prec|detc|expc|taxp|nilt|ftcr|pipc|admr|acrc|labc|appeal|acrs|educ|pcorp|pinst|trty|englaw) ;;
    *) die_input "target" ;;
  esac
}

validate_identifier() {
  [[ "$1" =~ ^[0-9]+$ ]] || die_input "MST/ID"
}

validate_article_number() {
  [[ "$1" =~ ^[0-9]+(의[0-9]+)?$ ]] || die_input "article number"
}

validate_effective_date() {
  [[ -z "$1" || "$1" =~ ^[0-9]{8}$ ]] || die_input "effective date"
}

validate_runtime_settings() {
  [[ "$CACHE_TTL_MIN" =~ ^[0-9]+$ ]] || die_input "cache TTL"
  [[ "${LAW_API_TIMEOUT:-30}" =~ ^[0-9]+$ ]] || die_input "timeout"
}

# 본문 조회 식별자 파라미터명: law/eflaw/englaw 는 MST(마스터번호), 그 외(admrul/ordin/prec 등)는 ID(일련번호)
# ※ eflaw(연혁법령)를 ID=로 호출하면 조회 실패 (2026-07-31 검증 세션에서 확인)
id_param() {
  case "$1" in
    law|eflaw|englaw) echo "MST" ;;
    *)                echo "ID" ;;
  esac
}

# 공통 HTTP 호출 (성공 응답만 캐시, TTL 내 재호출 시 캐시 반환)
fetch() {
  local url="$1"
  local key cachefile resp code body
  mkdir -p "$CACHE_DIR"
  chmod 700 "$CACHE_DIR"
  key=$(printf '%s' "$url" | python3 -c \
    'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')
  cachefile="${CACHE_DIR}/${key}"

  if [[ -s "$cachefile" && -n $(find "$cachefile" -mmin -"$CACHE_TTL_MIN" 2>/dev/null) ]]; then
    cat "$cachefile"
    return 0
  fi

  resp=$(printf 'url = "%s"\n' "$url" | \
    curl "${CURL_OPTS[@]}" --config - -w '\n__HTTP_CODE__:%{http_code}')
  code="${resp##*__HTTP_CODE__:}"
  body="${resp%$'\n'__HTTP_CODE__:*}"

  if [[ "$code" != "200" ]]; then
    echo "law_api: HTTP $code from $(redact_law_url "$url")" >&2
    printf '%s\n' "$body" | redact_law_text >&2
    return 1
  fi
  if [[ -z "$body" || "$body" == "null" ]]; then
    echo "law_api: empty response from $(redact_law_url "$url")" >&2
    return 1
  fi
  if ! python3 -c 'import json,sys; json.load(sys.stdin)' <<< "$body" 2>/dev/null; then
    echo "law_api: invalid JSON response from $(redact_law_url "$url")" >&2
    return 1
  fi

  printf '%s\n' "$body" > "${cachefile}.tmp.$$" && mv "${cachefile}.tmp.$$" "$cachefile"
  chmod 600 "$cachefile"
  printf '%s\n' "$body"
}

cmd="${1:-}"; shift || usage
validate_runtime_settings

case "$cmd" in

  search)
    (( $# == 2 || $# == 3 )) || usage
    target="${1:-}"; query="${2:-}"; display="${3:-20}"
    [[ -z "$target" || -z "$query" ]] && usage
    validate_target "$target"
    [[ "$display" =~ ^[0-9]+$ ]] && (( display >= 1 && display <= 100 )) || die_input "display"
    q=$(urlencode "$query")
    fetch "${BASE}/lawSearch.do?OC=${ENCODED_OC}&target=${target}&type=JSON&display=${display}&query=${q}"
    ;;

  get)
    (( $# == 2 || $# == 3 )) || usage
    target="${1:-}"; mst="${2:-}"; efyd="${3:-}"
    [[ -z "$target" || -z "$mst" ]] && usage
    validate_target "$target"
    validate_identifier "$mst"
    validate_effective_date "$efyd"
    url="${BASE}/lawService.do?OC=${ENCODED_OC}&target=${target}&type=JSON&$(id_param "$target")=${mst}"
    # eflaw(연혁법령)는 efYd 없이 호출하면 빈 응답({})을 반환 (2026-08-03 확인)
    [[ -n "$efyd" ]] && url="${url}&efYd=${efyd}"
    fetch "$url"
    ;;

  get-article)
    (( $# == 3 || $# == 4 )) || usage
    target="${1:-}"; mst="${2:-}"; jo="${3:-}"; efyd="${4:-}"
    [[ -z "$target" || -z "$mst" || -z "$jo" ]] && usage
    validate_target "$target"
    validate_identifier "$mst"
    validate_article_number "$jo"
    validate_effective_date "$efyd"
    url="${BASE}/lawService.do?OC=${ENCODED_OC}&target=${target}&type=JSON&$(id_param "$target")=${mst}"
    [[ -n "$efyd" ]] && url="${url}&efYd=${efyd}"
    body=$(fetch "$url") || exit 1
    python3 -c "
import json,re,sys
d=json.loads(sys.stdin.read())
jo=sys.argv[1]

# law: 법령 > 조문 > 조문단위 (구조화된 조문 객체)
# 장(章)·절(節) 제목이 같은 조문번호를 공유하는 경우가 있어(조문여부='전문')
# 실제 조문(조문여부='조문')을 우선 반환 (2026-07-28~31 검증 세션에서 반복 확인된 결함 수정)
arts=d.get('법령',{}).get('조문',{}).get('조문단위',[])
if isinstance(arts,dict): arts=[arts]
matches=[a for a in arts if str(a.get('조문번호',''))==jo]
found=[a for a in matches if a.get('조문여부')=='조문'] or matches
if found:
    print(json.dumps(found[0],ensure_ascii=False,indent=2))
    sys.exit(0)

# admrul: AdmRulService > 조문내용 (문자열 배열, '제N조(제목) ...' 형식)
adm=d.get('AdmRulService',{}).get('조문내용',[])
if isinstance(adm,str): adm=[adm]
pat=re.compile(r'^\s*제'+re.escape(jo)+r'조(?:의(\d+))?\s*[(（]')
found=[t for t in adm if isinstance(t,str) and pat.match(t)]
if found:
    print(json.dumps({'조문번호':jo,'조문내용':found},ensure_ascii=False,indent=2))
    sys.exit(0)

print(json.dumps({'error':f'제{jo}조 not found'},ensure_ascii=False))
" "$jo" <<< "$body"
    ;;

  list-annexes)
    (( $# == 1 )) || usage
    mst="${1:-}"
    [[ -z "$mst" ]] && usage
    validate_identifier "$mst"
    body=$(fetch "${BASE}/lawService.do?OC=${ENCODED_OC}&target=law&type=JSON&MST=${mst}") || exit 1
    python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
bl=d.get('법령',{}).get('별표',{}).get('별표단위',[])
if isinstance(bl,dict): bl=[bl]
out=[]
for b in bl:
    out.append({
        'no': b.get('별표번호',''),
        'sub': b.get('별표가지번호',''),
        'title': b.get('별표제목',''),
        'type': b.get('별표구분',''),
        'hwp': b.get('별표서식파일링크',''),
        'pdf': b.get('별표서식PDF파일링크',''),
        'hwp_name': b.get('별표HWP파일명',''),
    })
print(json.dumps(out,ensure_ascii=False,indent=2))
" <<< "$body"
    ;;

  get-annex)
    (( $# >= 2 && $# <= 4 )) || usage
    mst="${1:-}"; bl_no="${2:-}"; fmt="${3:-hwp}"; outdir="${4:-/tmp}"
    [[ -z "$mst" || -z "$bl_no" ]] && usage
    validate_identifier "$mst"
    [[ "$bl_no" =~ ^[0-9]+$ ]] || die_input "annex number"
    [[ "$fmt" == "hwp" || "$fmt" == "pdf" ]] || die_input "annex format"
    [[ -d "$outdir" && -w "$outdir" ]] || die_input "output directory"

    # 별표 목록에서 해당 번호 찾기
    body=$(fetch "${BASE}/lawService.do?OC=${ENCODED_OC}&target=law&type=JSON&MST=${mst}") || exit 1
    dl_info=$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
bl=d.get('법령',{}).get('별표',{}).get('별표단위',[])
if isinstance(bl,dict): bl=[bl]
target_no=sys.argv[1].zfill(4)
fmt=sys.argv[2]
for b in bl:
    if b.get('별표번호','').zfill(4)==target_no and b.get('별표가지번호','00')=='00':
        link=b.get('별표서식파일링크','') if fmt=='hwp' else b.get('별표서식PDF파일링크','')
        name=b.get('별표HWP파일명','') if fmt=='hwp' else b.get('별표PDF파일명','')
        title=b.get('별표제목','')
        print(json.dumps({'link':link,'name':name,'title':title},ensure_ascii=False))
        break
else:
    print(json.dumps({'error':f'별표 {sys.argv[1]} not found'}))
" "$bl_no" "$fmt" <<< "$body")

    link=$(printf '%s\n' "$dl_info" | python3 -c "import json,sys;print(json.load(sys.stdin).get('link',''))")
    name=$(printf '%s\n' "$dl_info" | python3 -c "import json,sys;print(json.load(sys.stdin).get('name',''))")
    err=$(printf '%s\n' "$dl_info" | python3 -c "import json,sys;print(json.load(sys.stdin).get('error',''))")

    if [[ -n "$err" ]]; then
      echo "law_api: $err" >&2
      exit 1
    fi
    if [[ -z "$link" ]]; then
      echo "law_api: no ${fmt} link for 별표 ${bl_no}" >&2
      exit 1
    fi

    outpath="${outdir}/${mst}_${bl_no}.${fmt}"
    download_tmp=$(mktemp "${outpath}.tmp.XXXXXX")
    if ! curl "${CURL_OPTS[@]}" --fail --location -o "$download_tmp" "${DL_BASE}${link}"; then
      rm -f -- "$download_tmp"
      echo "law_api: download failed" >&2
      exit 1
    fi

    if [[ ! -s "$download_tmp" ]]; then
      echo "law_api: download failed" >&2
      rm -f -- "$download_tmp"
      exit 1
    fi
    mv -f -- "$download_tmp" "$outpath"
    chmod 600 "$outpath"

    # 메타데이터 + 경로 출력
    printf '%s\n' "$dl_info" | python3 -c "
import json,sys
d=json.load(sys.stdin)
d['path']=sys.argv[1]
d['format']=sys.argv[2]
d['mst']=sys.argv[3]
print(json.dumps(d,ensure_ascii=False,indent=2))
" "$outpath" "$fmt" "$mst"
    ;;

  *) usage ;;
esac
