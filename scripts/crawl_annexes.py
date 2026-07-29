#!/usr/bin/env python3
"""100건+ 법령 별표 HWP/PDF 크롤러.

다양한 분야의 법령 시행령·시행규칙에서 별표를 수집하고
HWP 파일 + PDF 파일 + API JSON 별표내용을 함께 저장한다.
"""

import json, os, random, sys, time, urllib.parse, urllib.request, pathlib

OC = os.environ.get("LAW_API_OC", "<발급받은OC>")
BASE = "https://www.law.go.kr/DRF"
DL_BASE = "https://www.law.go.kr"

OUT = pathlib.Path("data/annex_samples")
HWP_DIR = OUT / "hwp"
PDF_DIR = OUT / "pdf"
JSON_DIR = OUT / "json_raw"

QUERIES = [
    "환경", "폐기물", "대기환경", "수질", "소음진동", "토양",
    "건축", "산업안전", "식품위생", "소방", "도로교통", "근로기준",
    "의료", "약사", "전기안전", "에너지", "화학물질", "광산",
    "항공안전", "선박", "원자력", "농약", "축산", "수산",
    "주택", "도시계획", "국토", "관세", "조세", "금융",
]

TARGET = 120  # 목표 수집 건수


def api_get(endpoint, params):
    params["OC"] = OC
    params["type"] = "JSON"
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  API error: {e}", file=sys.stderr)
        return None


def download(url_path, dest):
    url = f"{DL_BASE}{url_path}"
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"  DL error {url}: {e}", file=sys.stderr)
        return False


def main():
    for d in [HWP_DIR, PDF_DIR, JSON_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    index = []
    seen_keys = set()

    random.shuffle(QUERIES)

    for q in QUERIES:
        if len(index) >= TARGET:
            break

        print(f"\n[검색] query={q}")
        data = api_get("lawSearch.do", {"target": "law", "query": q, "display": "20"})
        if not data:
            continue

        laws = data.get("LawSearch", {}).get("law", [])
        if isinstance(laws, dict):
            laws = [laws]
        random.shuffle(laws)

        for law in laws:
            if len(index) >= TARGET:
                break

            mst = law.get("법령일련번호", "")
            name = law.get("법령명한글", "")
            if not mst:
                continue

            time.sleep(0.5)
            detail = api_get("lawService.do", {"target": "law", "MST": mst})
            if not detail or "법령" not in detail:
                continue

            bylaws = detail["법령"].get("별표", {}).get("별표단위", [])
            if not bylaws:
                continue
            if isinstance(bylaws, dict):
                bylaws = [bylaws]

            for bl in bylaws:
                if len(index) >= TARGET:
                    break

                hwp_link = bl.get("별표서식파일링크", "")
                pdf_link = bl.get("별표서식PDF파일링크", "")
                raw_content = bl.get("별표내용", "")
                bl_no = bl.get("별표번호", "0000")
                bl_sub = bl.get("별표가지번호", "00")
                title = bl.get("별표제목", "")

                key = f"{mst}_{bl_no}_{bl_sub}"
                if key in seen_keys or not hwp_link:
                    continue
                seen_keys.add(key)

                hwp_path = HWP_DIR / f"{key}.hwp"
                pdf_path = PDF_DIR / f"{key}.pdf"
                json_path = JSON_DIR / f"{key}.json"

                # HWP 다운로드
                if not download(hwp_link, hwp_path):
                    continue

                # 파일 검증 (최소 크기 + HWP 매직)
                if hwp_path.stat().st_size < 1024:
                    hwp_path.unlink(missing_ok=True)
                    continue

                # PDF 다운로드 (있으면)
                if pdf_link:
                    download(pdf_link, pdf_path)

                # API JSON 별표내용 저장
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "mst": mst,
                        "law_name": name,
                        "annex_no": bl_no,
                        "annex_sub": bl_sub,
                        "title": title,
                        "content": raw_content,
                    }, f, ensure_ascii=False, indent=2)

                entry = {
                    "key": key,
                    "mst": mst,
                    "law_name": name,
                    "annex_no": bl_no,
                    "annex_sub": bl_sub,
                    "title": title,
                    "hwp_link": hwp_link,
                    "pdf_link": pdf_link,
                    "hwp_file": str(hwp_path),
                    "pdf_file": str(pdf_path) if pdf_link else "",
                    "json_file": str(json_path),
                }
                index.append(entry)
                print(f"  [{len(index):3d}] {key} | {title[:40]}")

                time.sleep(0.3)

    # 인덱스 저장
    with open(OUT / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {len(index)}건 수집 → {OUT / 'index.json'}")


if __name__ == "__main__":
    main()
