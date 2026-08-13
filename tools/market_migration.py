#!/usr/bin/env python3
"""기존 demand_forecasts 행을 새 시장 스키마 또는 검토 큐로 분류한다."""
import hashlib
import re
from collections import Counter


VEHICLE_UNITS = {"대", "천대", "만대", "백만대"}
PERCENT_METRICS = {"성장률", "침투율", "점유율"}
SUPPORTED_REGIONS = {
    "글로벌": ("글로벌", None, "글로벌", None),
    "글로벌(중국 외)": ("글로벌", None, "글로벌", "중국 제외"),
    "북미": ("북미", "글로벌", "권역", None),
    "유럽": ("유럽", "글로벌", "권역", None),
    "기타": ("기타", "글로벌", "권역", None),
    "미국": ("미국", "북미", "국가", None),
    "중국": ("중국", "글로벌", "국가", None),
    "한국": ("한국", "글로벌", "국가", None),
}


def _contains(text, *terms):
    text = text.lower()
    return any(term.lower() in text for term in terms)


def _ess_dimensions(basis):
    application = "전체"
    if _contains(basis, "데이터센터", "data center"):
        application = "데이터센터"
    elif _contains(basis, "grid", "utility", "전력망", "계통", "그리드"):
        application = "Grid/Utility"
    elif _contains(basis, "c&i", "상업용", "산업용", "상업·산업"):
        application = "상업·산업용(C&I)"
    elif _contains(basis, "residential", "주거용"):
        application = "주거용"
    elif _contains(basis, "telecom", "통신"):
        application = "통신 등 기타"

    has_ups = bool(re.search(r"(?<![A-Za-z])UPS(?![A-Za-z])", basis, re.I))
    has_bess = bool(re.search(r"(?<![A-Za-z])BESS(?![A-Za-z])", basis, re.I))
    if has_ups and has_bess:
        return application, None, ["UPS·BESS 동시 표기"]
    return application, "UPS" if has_ups else "BESS" if has_bess else None, []


def _metric(row, market, basis):
    metric, unit = row.get("metric"), row.get("unit")
    if metric == "실적치":
        return None, ["실적치는 원문 지표 재확인 필요"]
    if metric == "수요량" and unit == "GWh":
        if market == "ESS" and _contains(
                basis, "설치량", "설치용량", "신규 설치", "설치 수요", "installation"):
            return "설치에너지", []
        return "수요량", []
    if metric == "판매대수":
        if unit not in VEHICLE_UNITS:
            return None, [f"지원하지 않는 지표·단위 조합: {metric}/{unit}"]
        if market != "EV":
            return None, [f"판매대수는 EV만 자동 이관: {market}"]
        return "판매대수", []
    if metric in PERCENT_METRICS and unit == "%":
        return metric, []
    return None, [f"지원하지 않는 지표·단위 조합: {metric}/{unit}"]


def _value_type(report, row, basis):
    if _contains(basis, "시나리오"):
        return "시나리오"
    report_year = int(str(report.get("date", "0000"))[:4])
    return "실적" if row["fy"] < report_year else "추정"


def _extraction(basis):
    if _contains(basis, "계산", "증감분"):
        return "계산", "파생"
    if _contains(basis, "본문"):
        return "본문", "근사"
    if _contains(basis, "차트"):
        return "차트", "근사"
    if _contains(basis, "표", "table"):
        return "표", "근사"
    return "원천불명", "근사"


def _ev_subsegment(basis):
    for pattern in (
            r"xEV", r"BEV\s*\+\s*PHEV", r"PHEV\s*\+\s*BEV",
            r"EV\s*\+\s*PHEV", r"PHEV\s*\+\s*EV",
            r"BEV", r"PHEV", r"HEV"):
        match = re.search(pattern, basis, re.I)
        if match:
            return match.group(0)
    for token in ("승용 전기차", "상용 전기차", "전기 버스", "전기 이륜·삼륜차"):
        if token in basis:
            return token
    return None


def _has_ambiguous_annual_period(report, row, basis):
    fy = row.get("fy")
    for year, _month in re.findall(r"(20\d{2})년\s*(1[0-2]|[1-9])월", basis):
        if isinstance(fy, int) and int(year) == fy:
            return True
    report_year = int(str(report.get("date", "0000"))[:4])
    has_month = bool(re.search(r"(?<!\d)(1[0-2]|[1-9])월", basis))
    has_flow_metric = _contains(basis, "판매", "출하", "설치", "누적", "월간")
    return fy == report_year and has_month and has_flow_metric


def _review_row(report, position, row, reasons):
    return {
        "report_id": report["report_id"],
        "date": report.get("date"),
        "house": report.get("house"),
        "origin_schema": "demand_forecasts",
        "legacy_row": position,
        "region": row.get("region"),
        "application": row.get("application"),
        "metric": row.get("metric"),
        "fy": row.get("fy"),
        "value": row.get("value"),
        "value_prev": row.get("value_prev"),
        "unit": row.get("unit"),
        "basis": row.get("basis"),
        "source_page": row.get("page"),
        "review_reasons": " | ".join(reasons),
    }


def _candidate(report, position, row):
    reasons = []
    basis = str(row.get("basis") or "").strip()
    if not basis:
        reasons.append("basis 누락")
    if not isinstance(row.get("fy"), int):
        reasons.append("fy 비정수")
    if not isinstance(row.get("value"), (int, float)):
        reasons.append("value 비숫자")
    if not isinstance(row.get("page"), int) or row.get("page", 0) < 1:
        reasons.append("페이지 누락 또는 오류")

    market = row.get("application")
    if market not in {"EV", "ESS"}:
        reasons.append(f"EV·ESS 외 application: {market}")

    raw_region = row.get("region")
    geography = SUPPORTED_REGIONS.get(raw_region)
    if geography is None:
        reasons.append(f"지원하지 않는 지역: {raw_region}")

    metric, metric_reasons = _metric(row, market, basis)
    reasons.extend(metric_reasons)
    if _has_ambiguous_annual_period(report, row, basis):
        reasons.append("월간·누적 자료는 period 재확인 필요")

    application, system_type = "전체", None
    if market == "ESS":
        application, system_type, system_reasons = _ess_dimensions(basis)
        reasons.extend(system_reasons)
    elif market == "EV" and _contains(basis, "UPS", "BESS"):
        reasons.append("EV 행에 ESS 시스템 형태 표기")

    review = _review_row(report, position, row, reasons)
    if reasons:
        return None, review, None

    geo_name, parent, level, scope_note = geography
    extraction_method, value_precision = _extraction(basis)
    value_type = _value_type(report, row, basis)
    subsegment_raw = _ev_subsegment(basis) if market == "EV" else None
    series_class = (
        "시나리오" if value_type == "시나리오"
        else "서브세그먼트" if application != "전체" or scope_note or subsegment_raw
        else "시장전체"
    )
    group = (
        market, application, system_type, raw_region, geo_name, parent, level,
        metric, row.get("unit"), subsegment_raw, basis, scope_note, row.get("page")
    )
    digest = hashlib.sha1("\x1f".join(str(item) for item in group).encode("utf-8")).hexdigest()[:10]
    converted = {
        "origin_schema": "demand_forecasts",
        "legacy_row": position,
        "series_id": f"legacy_p{row['page']}_{digest}",
        "market": market,
        "application": application,
        "system_type": system_type,
        "geography_raw": raw_region,
        "geography": geo_name,
        "parent_geography": parent,
        "geography_level": level,
        "metric": metric,
        "fy": row["fy"],
        "period": "FY",
        "value": row["value"],
        "value_prev": row.get("value_prev"),
        "unit": row["unit"],
        "value_type": value_type,
        "series_class": series_class,
        "subsegment_raw": subsegment_raw,
        "basis": basis,
        "scope_note": scope_note,
        "source_owner": None,
        "source_kind": "원천불명",
        "extraction_method": extraction_method,
        "value_precision": value_precision,
        "page": row["page"],
    }
    return converted, review, group


def migrate_legacy_demands(report):
    """한 리포트의 legacy 행을 (안전 이관, 수동 검토)로 빠짐없이 나눈다."""
    candidates, reviews = [], []
    for position, row in enumerate(report.get("demand_forecasts", []) or [], start=1):
        converted, review, group = _candidate(report, position, row)
        if converted is None:
            reviews.append(review)
        else:
            candidates.append((group, converted, review))

    observations = Counter(
        (group, item["fy"], item["period"]) for group, item, _ in candidates
    )
    conflicting_groups = {
        group for group, item, _ in candidates
        if observations[(group, item["fy"], item["period"])] > 1
    }

    migrated = []
    for group, item, review in candidates:
        if group in conflicting_groups:
            review["review_reasons"] = "같은 시리즈·기간에 복수 값 존재"
            reviews.append(review)
        else:
            migrated.append(item)

    expected = len(report.get("demand_forecasts", []) or [])
    if len(migrated) + len(reviews) != expected:
        raise RuntimeError(f"legacy 수요 이관 합계 불일치: {report.get('report_id')}")
    return migrated, reviews
