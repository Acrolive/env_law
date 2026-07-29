#!/usr/bin/env bash
# 국가법령정보 공동활용 OpenAPI curl 래퍼 (고도화)
#
# Usage:
#   law_api.sh search       <target> <query> [display=20]
#   law_api.sh get          <target> <MST|ID>
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
#   law, englaw          → MST= (법령 마스터번호)
#   admrul, ordin, prec 등 그 외 → ID= (일련번호)
#   ※ admrul을 MST=로 조회하면 "일치하는 행정규칙이 없습니다" 오류 반환 (2026-07-27 확인)
#
# env: LAW_API_OC (default: <발급받은OC>)

set -euo pipefail

OC="${LAW_API_OC:-<발급받은OC>}"
BASE="${LAW_API_BASE:-https://www.law.go.kr/DRF}"
DL_BASE="https://www.law.go.kr"

# 응답 캐시: 같은 질의 내에서 researcher/verifier/get-annex 가 동일 전문을
# 반복 조회하는 것을 방지. 캐시 내용은 API 응답 원문 그대로이므로 검증 원칙 유지.
CACHE_DIR="${LAW_API_CACHE_DIR:-/tmp/law_api_cache}"
CACHE_TTL_MIN="${LAW_API_CACHE_TTL_MIN:-60}"
CURL_OPTS=(-sS --max-time "${LAW_API_TIMEOUT:-30}" --retry 2 --retry-delay 1)

usage() {
  cat >&2 <<'EOF'
Usage:
  law_api.sh search       <target> <query> [display=20]
  law_api.sh get          <target> <MST|ID>
  law_api.sh get-article  <target> <MST|ID> <조번호> [efYd]
  law_api.sh list-annexes <MST>
  law_api.sh get-annex    <MST> <별표번호> [format=hwp|pdf] [outdir=/tmp]

식별자: law/englaw 는 MST(마스터번호), admrul/ordin/prec 등은 ID(일련번호) 자동 적용

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

env: LAW_API_OC (default: <발급받은OC>)
EOF
  exit 2
}

urlencode() {
  python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

# 본문 조회 식별자 파라미터명: law/englaw 는 MST(마스터번호), 그 외(admrul/ordin/prec 등)는 ID(일련번호)
id_param() {
  case "$1" in
    law|englaw) echo "MST" ;;
    *)          echo "ID" ;;
  esac
}

# 공통 HTTP 호출 (성공 응답만 캐시, TTL 내 재호출 시 캐시 반환)
fetch() {
  local url="$1"
  local key cachefile resp code body
  key=$(printf '%s' "$url" | sha256sum | cut -d' ' -f1)
  cachefile="${CACHE_DIR}/${key}"

  if [[ -s "$cachefile" && -n $(find "$cachefile" -mmin -"$CACHE_TTL_MIN" 2>/dev/null) ]]; then
    cat "$cachefile"
    return 0
  fi

  resp=$(curl "${CURL_OPTS[@]}" -w '\n__HTTP_CODE__:%{http_code}' "$url")
  code="${resp##*__HTTP_CODE__:}"
  body="${resp%$'\n'__HTTP_CODE__:*}"

  if [[ "$code" != "200" ]]; then
    echo "law_api: HTTP $code from $url" >&2
    echo "$body" >&2
    return 1
  fi
  if [[ -z "$body" || "$body" == "null" ]]; then
    echo "law_api: empty response from $url" >&2
    return 1
  fi

  mkdir -p "$CACHE_DIR"
  printf '%s\n' "$body" > "${cachefile}.tmp.$$" && mv "${cachefile}.tmp.$$" "$cachefile"
  printf '%s\n' "$body"
}

cmd="${1:-}"; shift || usage

case "$cmd" in

  search)
    target="${1:-}"; query="${2:-}"; display="${3:-20}"
    [[ -z "$target" || -z "$query" ]] && usage
    q=$(urlencode "$query")
    fetch "${BASE}/lawSearch.do?OC=${OC}&target=${target}&type=JSON&display=${display}&query=${q}"
    ;;

  get)
    target="${1:-}"; mst="${2:-}"
    [[ -z "$target" || -z "$mst" ]] && usage
    fetch "${BASE}/lawService.do?OC=${OC}&target=${target}&type=JSON&$(id_param "$target")=${mst}"
    ;;

  get-article)
    target="${1:-}"; mst="${2:-}"; jo="${3:-}"; efyd="${4:-}"
    [[ -z "$target" || -z "$mst" || -z "$jo" ]] && usage
    url="${BASE}/lawService.do?OC=${OC}&target=${target}&type=JSON&$(id_param "$target")=${mst}"
    [[ -n "$efyd" ]] && url="${url}&efYd=${efyd}"
    body=$(fetch "$url") || exit 1
    python3 -c "
import json,re,sys
d=json.loads(sys.stdin.read())
jo='${jo}'

# law: 법령 > 조문 > 조문단위 (구조화된 조문 객체)
arts=d.get('법령',{}).get('조문',{}).get('조문단위',[])
if isinstance(arts,dict): arts=[arts]
found=[a for a in arts if str(a.get('조문번호',''))==jo]
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
" <<< "$body"
    ;;

  list-annexes)
    mst="${1:-}"
    [[ -z "$mst" ]] && usage
    body=$(fetch "${BASE}/lawService.do?OC=${OC}&target=law&type=JSON&MST=${mst}") || exit 1
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
    mst="${1:-}"; bl_no="${2:-}"; fmt="${3:-hwp}"; outdir="${4:-/tmp}"
    [[ -z "$mst" || -z "$bl_no" ]] && usage

    # 별표 목록에서 해당 번호 찾기
    body=$(fetch "${BASE}/lawService.do?OC=${OC}&target=law&type=JSON&MST=${mst}") || exit 1
    dl_info=$(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
bl=d.get('법령',{}).get('별표',{}).get('별표단위',[])
if isinstance(bl,dict): bl=[bl]
target_no='${bl_no}'.zfill(4)
for b in bl:
    if b.get('별표번호','').zfill(4)==target_no and b.get('별표가지번호','00')=='00':
        link=b.get('별표서식파일링크','') if '${fmt}'=='hwp' else b.get('별표서식PDF파일링크','')
        name=b.get('별표HWP파일명','') if '${fmt}'=='hwp' else b.get('별표PDF파일명','')
        title=b.get('별표제목','')
        print(json.dumps({'link':link,'name':name,'title':title},ensure_ascii=False))
        break
else:
    print(json.dumps({'error':'별표 ${bl_no} not found'}))
" <<< "$body")

    link=$(echo "$dl_info" | python3 -c "import json,sys;print(json.load(sys.stdin).get('link',''))")
    name=$(echo "$dl_info" | python3 -c "import json,sys;print(json.load(sys.stdin).get('name',''))")
    err=$(echo "$dl_info" | python3 -c "import json,sys;print(json.load(sys.stdin).get('error',''))")

    if [[ -n "$err" ]]; then
      echo "law_api: $err" >&2
      exit 1
    fi
    if [[ -z "$link" ]]; then
      echo "law_api: no ${fmt} link for 별표 ${bl_no}" >&2
      exit 1
    fi

    outpath="${outdir}/${mst}_${bl_no}.${fmt}"
    curl "${CURL_OPTS[@]}" -o "$outpath" "${DL_BASE}${link}"

    if [[ ! -s "$outpath" ]]; then
      echo "law_api: download failed" >&2
      rm -f "$outpath"
      exit 1
    fi

    # 메타데이터 + 경로 출력
    echo "$dl_info" | python3 -c "
import json,sys
d=json.load(sys.stdin)
d['path']='${outpath}'
d['format']='${fmt}'
d['mst']='${mst}'
print(json.dumps(d,ensure_ascii=False,indent=2))
"
    ;;

  *) usage ;;
esac
