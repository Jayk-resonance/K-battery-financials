#!/usr/bin/env python3
"""전체 원본 PDF에서 시장·회사 물량 데이터 후보 페이지만 선별한다."""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "projects" / "market-data"

MARKET_TERMS = {
    "EV": ("전기차", "전기차용", "EV", "BEV", "PHEV", "xEV"),
    "ESS": ("ESS", "BESS", "에너지저장", "에너지 저장"),
}
COMPANY_TERMS = {
    "LG에너지솔루션": ("LG에너지솔루션", "LGES"),
    "삼성SDI": ("삼성SDI", "Samsung SDI"),
    "SK온": ("SK온", "SK on", "SK이노베이션"),
    "CATL": ("CATL",),
    "BYD": ("BYD",),
    "Panasonic": ("Panasonic", "파나소닉"),
    "CALB": ("CALB",),
    "Northvolt": ("Northvolt", "노스볼트"),
    "Tesla": ("Tesla", "테슬라"),
}
APPLICATION_TERMS = {
    "데이터센터": ("데이터센터", "data center", "datacenter"),
    "Grid/Utility": ("Grid", "Utility", "전력망", "계통"),
    "상업·산업용(C&I)": ("C&I", "상업용", "산업용"),
    "주거용": ("주거용", "residential"),
    "통신 등 기타": ("통신", "telecom"),
    "UPS": ("UPS",),
    "BESS": ("BESS",),
}
GEOGRAPHY_TERMS = {
    "글로벌": ("글로벌", "Global"),
    "북미": ("북미", "North America"),
    "미국": ("미국", "U.S.", "USA", "United States"),
    "유럽": ("유럽", "Europe"),
    "중국": ("중국", "China"),
    "한국": ("한국", "Korea"),
}
METRIC_TERMS = (
    "판매량", "판매대수", "출하량", "생산량", "생산능력", "설치량", "설치용량",
    "수요", "용량", "침투율", "점유율", "성장률", "YoY", "캐파", "CAPA", "capacity",
    "shipment", "sales", "installation",
)
COMPANY_METRIC_TERMS = (
    "판매량", "출하량", "생산량", "생산능력", "캐파", "CAPA", "capacity", "shipment", "sales",
)
ENERGY_UNIT_RE = re.compile(r"(?<![A-Za-z])(MWh|GWh|TWh|MW|GW)(?![A-Za-z])", re.I)
VEHICLE_VALUE_RE = re.compile(r"\d[\d,.]*\s*(백만대|만대|천대|대)")
PERCENT_VALUE_RE = re.compile(r"\d[\d,.]*\s*(%)")
YEAR_RE = re.compile(r"20\d{2}")


def _contains(text, term):
    if re.fullmatch(r"[A-Za-z&. ]+", term):
        return re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text, re.I) is not None
    return term.lower() in text.lower()


def _matches(text, vocabulary):
    return [name for name, terms in vocabulary.items()
            if any(_contains(text, term) for term in terms)]


def classify_page(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    markets = _matches(text, MARKET_TERMS)
    companies = _matches(text, COMPANY_TERMS)
    applications = _matches(text, APPLICATION_TERMS)
    geographies = _matches(text, GEOGRAPHY_TERMS)
    metrics = [term for term in METRIC_TERMS if _contains(text, term)]
    company_metrics = [term for term in COMPANY_METRIC_TERMS if _contains(text, term)]
    energy_units = {match.upper() for match in ENERGY_UNIT_RE.findall(text)}
    vehicle_units = set(VEHICLE_VALUE_RE.findall(text))
    percent_units = set(PERCENT_VALUE_RE.findall(text))
    units = sorted(energy_units | vehicle_units | percent_units)
    has_time_or_values = bool(YEAR_RE.search(text)) or len(re.findall(r"\d[\d,.]*", text)) >= 3

    market_candidate = bool(
        markets and metrics and (energy_units or vehicle_units or percent_units) and has_time_or_values
    )
    company_candidate = bool(companies and company_metrics and energy_units and has_time_or_values)
    if not market_candidate and not company_candidate:
        return None

    candidate_type = (
        "시장·회사" if market_candidate and company_candidate
        else "시장" if market_candidate else "회사"
    )
    score = (
        3 + min(len(units), 2) + min(len(metrics), 2)
        + (2 if markets else 0) + (2 if companies else 0)
        + (1 if applications else 0) + (1 if geographies else 0)
        + (1 if YEAR_RE.search(text) else 0)
    )
    risk_flags = []
    if any(_contains(text, term) for term in ("수주", "공급계약", "공급 계약", "백로그", "backlog")):
        risk_flags.append("수주·계약")
    return {
        "selection_reason": "정량키워드",
        "candidate_type": candidate_type,
        "markets": "|".join(markets),
        "companies": "|".join(companies),
        "applications": "|".join(applications),
        "geographies": "|".join(geographies),
        "metrics": "|".join(metrics),
        "company_metrics": "|".join(company_metrics),
        "units": "|".join(units),
        "risk_flags": "|".join(risk_flags),
        "score": score,
    }


def _load_source_context():
    manifest = json.loads((ROOT / ".staging" / "manifest.json").read_text(encoding="utf-8"))
    inbox_ids = defaultdict(list)
    for row in manifest:
        inbox_ids[row["file"]].append(row["report_id"])

    actual_ids = defaultdict(set)
    for path in (ROOT / ".staging").glob("*.json"):
        if path.name == "manifest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        document_id = data.get("document_id") or data.get("report_id") or data.get("company")
        if not document_id:
            continue
        for match in re.findall(r'[^"\\/]+\.pdf', json.dumps(data, ensure_ascii=False), re.I):
            actual_ids[match].add(str(document_id))

    legacy_pages = defaultdict(set)
    for path in (ROOT / ".staging").glob("*.json"):
        if path.name == "manifest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        rid = data.get("report_id")
        if not rid:
            continue
        for row in data.get("demand_forecasts", []) or []:
            if isinstance(row.get("page"), int):
                legacy_pages[rid].add(row["page"])
    return inbox_ids, actual_ids, legacy_pages


def build_candidate_files():
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise SystemExit("pypdfium2가 필요합니다. Codex bundled Python으로 실행하세요.") from exc

    inbox_ids, actual_ids, legacy_pages = _load_source_context()
    candidates = []
    inventory = []
    pdfs = sorted((ROOT / "inbox").glob("*.pdf")) + sorted((ROOT / "actuals").glob("*.pdf"))
    for pdf_path in pdfs:
        source_group = pdf_path.parent.name
        ids = inbox_ids.get(pdf_path.name, []) if source_group == "inbox" else actual_ids.get(pdf_path.name, set())
        source_ids = "|".join(sorted(ids))
        extracted_pages = candidate_count = 0
        error = ""
        try:
            document = pdfium.PdfDocument(str(pdf_path))
            page_count = len(document)
            for page_number in range(1, page_count + 1):
                try:
                    page = document[page_number - 1]
                    text_page = page.get_textpage()
                    text = text_page.get_text_range() or ""
                    text_page.close()
                    page.close()
                except Exception:
                    text = ""
                if text.strip():
                    extracted_pages += 1
                covered = any(page_number in legacy_pages[rid] for rid in ids)
                classified = classify_page(text)
                if not classified and not covered:
                    continue
                if not classified:
                    classified = {
                        "selection_reason": "기존시장데이터",
                        "candidate_type": "기존시장",
                        "markets": "",
                        "companies": "",
                        "applications": "",
                        "geographies": "",
                        "metrics": "",
                        "company_metrics": "",
                        "units": "",
                        "risk_flags": "",
                        "score": 0,
                    }
                elif covered:
                    classified["selection_reason"] = "정량키워드+기존시장데이터"
                candidate_count += 1
                priority = _priority(source_group, covered, classified)
                candidates.append({
                    "source_group": source_group,
                    "source_file": pdf_path.name,
                    "source_ids": source_ids,
                    "page": page_number,
                    "page_count": page_count,
                    "legacy_covered": "Y" if covered else "N",
                    "priority": priority,
                    **classified,
                    "visual_review_status": "대기",
                })
            document.close()
        except Exception as exc:
            page_count = 0
            error = f"{type(exc).__name__}: {exc}"
        inventory.append({
            "source_group": source_group,
            "source_file": pdf_path.name,
            "source_ids": source_ids,
            "page_count": page_count,
            "text_extracted_pages": extracted_pages,
            "candidate_pages": candidate_count,
            "requires_ocr": "Y" if page_count and extracted_pages == 0 else "N",
            "error": error,
        })

    candidates.sort(key=lambda row: (
        row["legacy_covered"] == "Y", -row["score"], row["source_group"],
        row["source_file"], row["page"]
    ))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inventory_path = OUTPUT_DIR / "pdf_inventory.csv"
    candidate_path = OUTPUT_DIR / "backfill_candidates.csv"
    _write_csv(inventory_path, inventory)
    _write_csv(candidate_path, candidates)
    return inventory_path, candidate_path, inventory, candidates


def _priority(source_group, covered, classified):
    if covered:
        return "AUDIT"
    score = classified["score"]
    if "수주·계약" in classified["risk_flags"] and not classified["company_metrics"]:
        return "P3"
    if score >= 13 or (score >= 12 and classified["applications"]):
        return "P1"
    if source_group == "actuals" and "회사" in classified["candidate_type"]:
        return "P1"
    return "P2" if score >= 10 else "P3"


def _write_csv(path, rows):
    if not rows:
        raise ValueError(f"기록할 행이 없습니다: {path.name}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    inventory_path, candidate_path, inventory, candidates = build_candidate_files()
    uncovered = sum(row["legacy_covered"] == "N" for row in candidates)
    ocr = sum(row["requires_ocr"] == "Y" for row in inventory)
    print(f"PDF {len(inventory)}개, 후보 {len(candidates)}페이지, 미등재 후보 {uncovered}페이지, OCR 필요 {ocr}개")
    print(inventory_path.relative_to(ROOT))
    print(candidate_path.relative_to(ROOT))
