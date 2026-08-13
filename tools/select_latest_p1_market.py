#!/usr/bin/env python3
"""P1 시장 후보를 2026년 하우스·시장·커버리지별 최신 자료로 재분류한다."""

import csv
import datetime as dt
import os
from collections import Counter, defaultdict


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.join(ROOT, "projects", "market-data")
CANDIDATE_PATH = os.path.join(PROJECT_DIR, "backfill_candidates.csv")
CATALOG_PATH = os.path.join(ROOT, "index", "report_catalog.csv")
OUTPUT_PATH = os.path.join(PROJECT_DIR, "p1_market_reclassification.csv")
SOURCE_OUTPUT_PATH = os.path.join(PROJECT_DIR, "p1_market_latest_sources.csv")
TARGET_REPORT_YEAR = "2026"

CLASS_ORDER = {
    "최신 유효": 1,
    "과거 고유 검토": 2,
    "추가 검토": 3,
    "회사공시 별도": 4,
    "중복·구형 제외": 5,
    "연도 범위 제외": 6,
}


def split_pipe(value):
    return {item for item in (value or "").split("|") if item}


def p1_market_scope(rows):
    return [
        row for row in rows
        if row.get("priority") == "P1"
        and "시장" in (row.get("candidate_type") or "")
        and row.get("visual_review_status") == "대기"
    ]


def select_latest_sources(candidates, catalog):
    """하우스·시장·커버리지별로 최신 report ID 하나를 고른다."""
    groups = defaultdict(lambda: defaultdict(list))
    for row in candidates:
        if row.get("source_group") != "inbox":
            continue
        report_id = row.get("source_ids")
        meta = catalog.get(report_id)
        if not meta:
            continue
        if not meta["date"].startswith(f"{TARGET_REPORT_YEAR}-"):
            continue
        for market in split_pipe(row.get("markets")):
            key = (meta["house"], market, meta["coverage"])
            groups[key][report_id].append(row)

    selected = {}
    for key, sources in groups.items():
        def rank(report_id):
            rows = sources[report_id]
            return (
                catalog[report_id]["date"],
                len(rows),
                max(int(row.get("score") or 0) for row in rows),
                report_id,
            )

        selected[key] = max(sources, key=rank)
    return groups, selected


def classify_candidates(candidates, catalog):
    groups, selected = select_latest_sources(candidates, catalog)
    selected_ids = set(selected.values())
    anchor_date = max(
        dt.date.fromisoformat(catalog[row["source_ids"]]["date"])
        for row in candidates if row.get("source_ids") in catalog
    )
    covered_applications = {}
    for key, sources in groups.items():
        winner = selected[key]
        covered_applications[key] = set().union(*(
            split_pipe(row.get("applications")) for row in sources[winner]
        ))

    results = []
    for row in candidates:
        result = dict(row)
        report_id = row.get("source_ids")
        meta = catalog.get(report_id)
        unique_applications = set()
        references = set()
        age_days = None
        freshness = ""

        if row.get("source_group") == "actuals":
            classification = "회사공시 별도"
            reason = "증권사 하우스 선별 대상이 아니므로 회사 공시 트랙에서 별도 검토"
            house = "회사공시"
            coverage = report_id or ""
            report_date = ""
            report_title = os.path.splitext(row.get("source_file") or "")[0]
        elif not meta:
            classification = "추가 검토"
            reason = "리포트 카탈로그에서 report ID를 찾지 못해 자동 최신 판정 불가"
            house = ""
            coverage = ""
            report_date = ""
            report_title = ""
        else:
            house = meta["house"]
            coverage = meta["coverage"]
            report_date = meta["date"]
            report_title = meta["report_title"]
            age_days = (anchor_date - dt.date.fromisoformat(report_date)).days
            freshness = "최근 1년" if age_days <= 365 else "1년 초과"
            if not report_date.startswith(f"{TARGET_REPORT_YEAR}-"):
                classification = "연도 범위 제외"
                reason = f"{TARGET_REPORT_YEAR}년 발간 리포트만 분석"
            else:
                for market in split_pipe(row.get("markets")):
                    key = (house, market, coverage)
                    if key in selected:
                        references.add(selected[key])
                        unique_applications |= (
                            split_pipe(row.get("applications"))
                            - covered_applications[key]
                        )

                if report_id in selected_ids:
                    selected_markets = sorted(
                        market for (group_house, market, group_coverage), winner
                        in selected.items()
                        if winner == report_id
                        and group_house == house and group_coverage == coverage
                    )
                    classification = "최신 유효"
                    reason = (
                        f"{house}·{coverage}의 {TARGET_REPORT_YEAR}년 최신 "
                        f"{'/'.join(selected_markets)} 자료"
                    )
                elif coverage == "산업" and unique_applications:
                    classification = "과거 고유 검토"
                    reason = "최신 산업 자료에 없는 Application 신호: " + ", ".join(sorted(unique_applications))
                elif unique_applications and not row.get("risk_flags"):
                    classification = "추가 검토"
                    reason = "최신 자료에 없는 Application 신호: " + ", ".join(sorted(unique_applications))
                else:
                    classification = "중복·구형 제외"
                    reason = "동일 하우스·시장·커버리지의 2026년 최신 자료로 대체"
                    if row.get("risk_flags"):
                        reason += f"; 위험 신호 {row['risk_flags']}"

        result.update({
            "house": house,
            "coverage": coverage,
            "report_date": report_date,
            "report_title": report_title,
            "reclassification": classification,
            "decision_reason": reason,
            "latest_reference_ids": "|".join(sorted(references)),
            "unique_application_signals": "|".join(sorted(unique_applications)),
            "selection_anchor_date": anchor_date.isoformat(),
            "age_days": "" if age_days is None else age_days,
            "freshness": freshness,
        })
        results.append(result)

    results.sort(key=lambda row: (
        CLASS_ORDER[row["reclassification"]],
        row.get("house") or "",
        row.get("report_date") or "",
        row.get("source_ids") or "",
        int(row.get("page") or 0),
    ))
    return results, groups, selected


def write_outputs(results, groups, selected):
    fields = [
        "reclassification", "decision_reason", "house", "coverage",
        "report_date", "report_title", "source_group", "source_file",
        "source_ids", "page", "page_count", "candidate_type", "markets",
        "applications", "geographies", "metrics", "units", "risk_flags",
        "score", "latest_reference_ids", "unique_application_signals",
        "selection_anchor_date", "age_days", "freshness",
    ]
    with open(OUTPUT_PATH, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    source_fields = [
        "house", "market", "coverage", "selected_report_id", "date",
        "report_title", "candidate_pages", "age_days", "freshness",
        "selection_basis",
    ]
    with open(SOURCE_OUTPUT_PATH, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=source_fields)
        writer.writeheader()
        for key in sorted(selected):
            house, market, coverage = key
            report_id = selected[key]
            rows = groups[key][report_id]
            writer.writerow({
                "house": house,
                "market": market,
                "coverage": coverage,
                "selected_report_id": report_id,
                "date": next(row["report_date"] for row in results
                             if row.get("source_ids") == report_id),
                "report_title": next(row["report_title"] for row in results
                                     if row.get("source_ids") == report_id),
                "candidate_pages": len(rows),
                "age_days": next(row["age_days"] for row in results
                                 if row.get("source_ids") == report_id),
                "freshness": next(row["freshness"] for row in results
                                  if row.get("source_ids") == report_id),
                "selection_basis": "동일 하우스·시장·커버리지에서 발간일 최신; 페이지 수·점수는 동률 보조",
            })


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    candidates = p1_market_scope(load_csv(CANDIDATE_PATH))
    catalog = {row["report_id"]: row for row in load_csv(CATALOG_PATH)}
    results, groups, selected = classify_candidates(candidates, catalog)
    write_outputs(results, groups, selected)
    counts = Counter(row["reclassification"] for row in results)
    print(f"P1 시장 후보 {len(results)}페이지 재분류")
    for classification in CLASS_ORDER:
        print(f"- {classification}: {counts[classification]}페이지")
    print(f"- {TARGET_REPORT_YEAR}년 하우스별 선정 report ID: {len(set(selected.values()))}개")


if __name__ == "__main__":
    main()
