#!/usr/bin/env python3
"""3-way 비교: kordoc(HWP→HTML/MD) vs pdftotext(PDF→텍스트) vs API JSON 별표내용.

텍스트 내용 일치율, 테이블 구조 유무, 실패 패턴을 분석하여
evaluation_report.json + evaluation_report.md 를 생성한다.
"""

import json, os, re, unicodedata, pathlib
from html.parser import HTMLParser
from difflib import SequenceMatcher

SAMPLES = pathlib.Path("data/annex_samples")
RESULTS = pathlib.Path("data/annex_results")
KORDOC_DIR = RESULTS / "kordoc"
PDFTEXT_DIR = RESULTS / "pdftotext"
JSON_DIR = SAMPLES / "json_raw"


class HTMLTextExtractor(HTMLParser):
    """HTML 태그를 제거하고 텍스트만 추출."""
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def get_text(self):
        return " ".join(self.parts)


class HTMLTableExtractor(HTMLParser):
    """HTML에서 테이블 구조(행 수, 열 수, 셀 텍스트 목록) 추출."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_cell = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.current_table = {"rows": [], "has_colspan": False, "has_rowspan": False}
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.in_cell = True
            self.current_cell = []
            attrs_dict = dict(attrs)
            if "colspan" in attrs_dict:
                self.current_table["has_colspan"] = True
            if "rowspan" in attrs_dict:
                self.current_table["has_rowspan"] = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.current_row.append(" ".join(self.current_cell).strip())
            self.in_cell = False
            self.current_cell = []
        elif tag == "tr" and self.current_row is not None and self.current_table is not None:
            self.current_table["rows"].append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.current_table is not None:
            self.tables.append(self.current_table)
            self.current_table = None

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data.strip())


def normalize(text):
    """비교를 위한 텍스트 정규화."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[│├┤┬┴┼─┌┐└┘╔╗╚╝║═]", "", text)  # ASCII 박스 문자 제거
    text = text.strip()
    return text


def extract_text_from_html(md):
    """kordoc 마크다운(HTML 포함)에서 순수 텍스트 추출."""
    ext = HTMLTextExtractor()
    ext.feed(md)
    return normalize(ext.get_text())


def extract_tables_from_html(md):
    """kordoc 출력에서 테이블 구조 추출."""
    ext = HTMLTableExtractor()
    ext.feed(md)
    return ext.tables


def extract_text_from_json_content(content):
    """API JSON 별표내용에서 텍스트 추출."""
    if isinstance(content, list):
        parts = []
        for row in content:
            if isinstance(row, list):
                for cell in row:
                    t = normalize(str(cell))
                    if t:
                        parts.append(t)
            else:
                t = normalize(str(row))
                if t:
                    parts.append(t)
        return " ".join(parts)
    return normalize(str(content))


def similarity(a, b):
    """두 문자열의 유사도 (0~1)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def main():
    index = json.load(open(SAMPLES / "index.json", encoding="utf-8"))
    print(f"총 {len(index)}건 비교 시작\n")

    results = []

    for entry in index:
        key = entry["key"]
        r = {"key": key, "title": entry.get("title", ""), "law_name": entry.get("law_name", "")}

        # kordoc 결과
        kordoc_path = KORDOC_DIR / f"{key}.md"
        kordoc_text = ""
        kordoc_tables = []
        if kordoc_path.exists():
            md = kordoc_path.read_text(encoding="utf-8")
            kordoc_text = extract_text_from_html(md)
            kordoc_tables = extract_tables_from_html(md)
            r["kordoc_ok"] = True
            r["kordoc_len"] = len(kordoc_text)
            r["kordoc_table_count"] = len(kordoc_tables)
            r["kordoc_has_colspan"] = any(t["has_colspan"] for t in kordoc_tables)
            r["kordoc_has_rowspan"] = any(t["has_rowspan"] for t in kordoc_tables)
            r["kordoc_total_rows"] = sum(len(t["rows"]) for t in kordoc_tables)
        else:
            r["kordoc_ok"] = False
            r["kordoc_len"] = 0

        # pdftotext 결과
        pdf_path = PDFTEXT_DIR / f"{key}.txt"
        pdf_text = ""
        if pdf_path.exists():
            pdf_text = normalize(pdf_path.read_text(encoding="utf-8"))
            r["pdftotext_ok"] = True
            r["pdftotext_len"] = len(pdf_text)
        else:
            r["pdftotext_ok"] = False
            r["pdftotext_len"] = 0

        # API JSON 별표내용
        json_path = JSON_DIR / f"{key}.json"
        json_text = ""
        if json_path.exists():
            jdata = json.load(open(json_path, encoding="utf-8"))
            json_text = extract_text_from_json_content(jdata.get("content", ""))
            r["json_ok"] = True
            r["json_len"] = len(json_text)
        else:
            r["json_ok"] = False
            r["json_len"] = 0

        # 유사도 계산
        r["sim_kordoc_pdf"] = round(similarity(kordoc_text, pdf_text), 4)
        r["sim_kordoc_json"] = round(similarity(kordoc_text, json_text), 4)
        r["sim_pdf_json"] = round(similarity(pdf_text, json_text), 4)

        # 패턴 분류
        if r.get("kordoc_has_rowspan") or r.get("kordoc_has_colspan"):
            r["complexity"] = "complex_merge"
        elif r.get("kordoc_table_count", 0) > 0:
            r["complexity"] = "simple_table"
        else:
            r["complexity"] = "text_only"

        results.append(r)

    # 통계 계산
    total = len(results)
    kordoc_success = sum(1 for r in results if r["kordoc_ok"])
    pdf_success = sum(1 for r in results if r["pdftotext_ok"])

    sims_kp = [r["sim_kordoc_pdf"] for r in results if r["kordoc_ok"] and r["pdftotext_ok"]]
    sims_kj = [r["sim_kordoc_json"] for r in results if r["kordoc_ok"] and r["json_ok"]]
    sims_pj = [r["sim_pdf_json"] for r in results if r["pdftotext_ok"] and r["json_ok"]]

    avg = lambda lst: round(sum(lst)/len(lst), 4) if lst else 0

    # 복잡도별 통계
    complexity_stats = {}
    for comp in ["complex_merge", "simple_table", "text_only"]:
        subset = [r for r in results if r.get("complexity") == comp]
        if subset:
            complexity_stats[comp] = {
                "count": len(subset),
                "avg_sim_kordoc_pdf": avg([r["sim_kordoc_pdf"] for r in subset]),
                "avg_sim_kordoc_json": avg([r["sim_kordoc_json"] for r in subset]),
                "avg_sim_pdf_json": avg([r["sim_pdf_json"] for r in subset]),
            }

    # 낮은 유사도 사례 (kordoc vs pdf < 0.5)
    low_sim = [r for r in results if r["sim_kordoc_pdf"] < 0.5 and r["kordoc_ok"] and r["pdftotext_ok"]]

    report = {
        "total_samples": total,
        "kordoc": {"success": kordoc_success, "rate": round(kordoc_success/total, 4)},
        "pdftotext": {"success": pdf_success, "rate": round(pdf_success/total, 4)},
        "similarity": {
            "kordoc_vs_pdftotext": {"avg": avg(sims_kp), "min": round(min(sims_kp), 4) if sims_kp else 0, "max": round(max(sims_kp), 4) if sims_kp else 0},
            "kordoc_vs_json": {"avg": avg(sims_kj), "min": round(min(sims_kj), 4) if sims_kj else 0, "max": round(max(sims_kj), 4) if sims_kj else 0},
            "pdftotext_vs_json": {"avg": avg(sims_pj), "min": round(min(sims_pj), 4) if sims_pj else 0, "max": round(max(sims_pj), 4) if sims_pj else 0},
        },
        "complexity_breakdown": complexity_stats,
        "low_similarity_cases": [{"key": r["key"], "title": r["title"], "sim_kordoc_pdf": r["sim_kordoc_pdf"], "complexity": r["complexity"]} for r in low_sim],
        "table_stats": {
            "with_tables": sum(1 for r in results if r.get("kordoc_table_count", 0) > 0),
            "with_colspan": sum(1 for r in results if r.get("kordoc_has_colspan")),
            "with_rowspan": sum(1 for r in results if r.get("kordoc_has_rowspan")),
        },
    }

    # JSON 보고서
    json.dump(report, open(RESULTS / "evaluation_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 상세 결과
    json.dump(results, open(RESULTS / "evaluation_details.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 마크다운 보고서
    md_lines = [
        "# 별표 이중 파서 실증 평가 보고서\n",
        f"**총 샘플**: {total}건\n",
        "## 1. 파싱 성공률\n",
        f"| 엔진 | 성공 | 실패 | 성공률 |",
        f"|---|---|---|---|",
        f"| kordoc (HWP→MD) | {kordoc_success} | {total - kordoc_success} | {report['kordoc']['rate']*100:.1f}% |",
        f"| pdftotext (PDF→텍스트) | {pdf_success} | {total - pdf_success} | {report['pdftotext']['rate']*100:.1f}% |",
        "",
        "## 2. 텍스트 유사도 (정규화 후)\n",
        f"| 비교 쌍 | 평균 | 최소 | 최대 |",
        f"|---|---|---|---|",
    ]
    for pair, label in [("kordoc_vs_pdftotext", "kordoc ↔ pdftotext"),
                        ("kordoc_vs_json", "kordoc ↔ API JSON"),
                        ("pdftotext_vs_json", "pdftotext ↔ API JSON")]:
        s = report["similarity"][pair]
        md_lines.append(f"| {label} | {s['avg']*100:.1f}% | {s['min']*100:.1f}% | {s['max']*100:.1f}% |")

    md_lines += [
        "",
        "## 3. 테이블 구조 통계\n",
        f"- 테이블 포함 별표: {report['table_stats']['with_tables']}건 / {total}건",
        f"- colspan 포함: {report['table_stats']['with_colspan']}건",
        f"- rowspan 포함: {report['table_stats']['with_rowspan']}건",
        "",
        "## 4. 복잡도별 유사도\n",
        "| 유형 | 건수 | kordoc↔pdf | kordoc↔json | pdf↔json |",
        "|---|---|---|---|---|",
    ]
    for comp, stats in complexity_stats.items():
        md_lines.append(
            f"| {comp} | {stats['count']} | {stats['avg_sim_kordoc_pdf']*100:.1f}% | "
            f"{stats['avg_sim_kordoc_json']*100:.1f}% | {stats['avg_sim_pdf_json']*100:.1f}% |"
        )

    if low_sim:
        md_lines += [
            "",
            f"## 5. 낮은 유사도 사례 (kordoc↔pdf < 50%) — {len(low_sim)}건\n",
            "| key | 제목 | 유사도 | 유형 |",
            "|---|---|---|---|",
        ]
        for r in low_sim:
            md_lines.append(f"| {r['key']} | {r['title'][:30]} | {r['sim_kordoc_pdf']*100:.1f}% | {r['complexity']} |")

    md_lines += [
        "",
        "## 6. 결론 및 권장사항\n",
        f"*평가 데이터 기반 자동 생성. {total}건 분석.*",
    ]

    # 자동 권장사항
    avg_kp = avg(sims_kp)
    if kordoc_success == total and avg_kp >= 0.85:
        md_lines.append(f"\n**kordoc 단독 사용 가능** — 성공률 100%, 평균 유사도 {avg_kp*100:.1f}%.")
    elif kordoc_success == total and avg_kp >= 0.70:
        md_lines.append(f"\n**kordoc 기본 + 낮은 유사도 케이스 수동 검증 권장** — 평균 유사도 {avg_kp*100:.1f}%.")
    else:
        md_lines.append(f"\n**추가 파서 도입 또는 PDF 폴백 전략 필요** — 성공률 {report['kordoc']['rate']*100:.1f}%, 유사도 {avg_kp*100:.1f}%.")

    (RESULTS / "evaluation_report.md").write_text("\n".join(md_lines), encoding="utf-8")

    print("=== 평가 완료 ===")
    print(f"kordoc 성공률: {report['kordoc']['rate']*100:.1f}%")
    print(f"pdftotext 성공률: {report['pdftotext']['rate']*100:.1f}%")
    print(f"유사도 (kordoc↔pdf): avg {avg_kp*100:.1f}%, min {min(sims_kp)*100:.1f}%")
    print(f"유사도 (kordoc↔json): avg {avg(sims_kj)*100:.1f}%")
    print(f"테이블: {report['table_stats']['with_tables']}건, colspan: {report['table_stats']['with_colspan']}, rowspan: {report['table_stats']['with_rowspan']}")
    print(f"낮은 유사도 (<50%): {len(low_sim)}건")
    print(f"\n보고서: {RESULTS / 'evaluation_report.md'}")


if __name__ == "__main__":
    main()
