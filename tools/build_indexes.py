#!/usr/bin/env python3
"""스테이징 JSON -> 표준 MD + 인덱스 재빌드 (스키마 v2).

사용법:
  python3 tools/build_indexes.py           # 검증 + 렌더 + 인덱스
  python3 tools/build_indexes.py --check   # 검증만 (파일 안 씀)
  python3 tools/build_indexes.py --check-id <report_id>  # 지정 리포트 엄격 검증
  python3 tools/build_indexes.py --force   # DB 축소 안전장치 무시 (의도적 삭제 시에만)

주의: .staging 을 유일한 소스로 index/ 와 reports/ 를 전량 덮어쓴다.
      staging 이 없거나 일부만 있으면 DB가 지워지므로, 리포트 수가 줄어드는
      재빌드는 자동으로 중단된다(--force 로만 강행).

입력:  .staging/<report_id>.json (리포트), .staging/actuals_*.json (IR)
출력:  reports/<YYYY>/<report_id>.md
       index/reports.jsonl, estimates.csv, stances.csv,
       industry_views.csv, actuals.csv, drivers.csv
"""
import argparse, json, csv, os, sys, glob, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGING = os.path.join(ROOT, ".staging")
SEG_STD = {"전사", "배터리합계", "소형", "중대형", "EV", "ESS", "전자재료", "기타"}
AMPC_BASIS = {"excl", "incl", "incl_unknown", "na"}
PERIODS = {"FY", "1Q", "2Q", "3Q", "4Q"}
OPINIONS = {"매수", "중립", "매도", None}

COMPANY_STD = {"LG에너지솔루션": "LGES", "엘지에너지솔루션": "LGES", "LG Energy Solution": "LGES"}
# metric 통제어휘 (NORMALIZATION.md §9). 대시보드는 매출/영업이익/AMPC 만 집계하므로
# 동의어가 갈리면 그 리포트의 값이 조용히 누락된다 — 인제스트 시 여기서 통일한다.
METRIC_STD = {"매출액": "매출", "AMPC(Tax Credit)": "AMPC",
              "지배주주순익": "지배주주순이익", "지배순이익": "지배주주순이익"}
METRICS = {"매출", "영업이익", "AMPC", "순이익", "지배주주순이익", "출하량", "점유율"}
BODY_KEYS = ("summary", "valuation", "segment_pl", "issue_comments", "risks", "quotes")
# stances.issue와 themes.theme의 집계 키. key_issues와 summary는 원문 세부 표현을 보존한다.
ISSUES = {"LFP", "46파이", "ESS", "북미CAPEX", "수율", "AMPC", "OEM보상금",
          "파우치", "전고체", "밸류에이션", "소형전지", "유럽EV", "북미EV",
          "중국경쟁", "관세", "로봇", "배터리판매량"}
ISSUE_STD = {"북미 ESS": "ESS", "북미ESS": "ESS",
             "IRA AMPC": "AMPC", "IRA AMPC 수혜": "AMPC",
             "4680": "46파이", "46 시리즈": "46파이", "46시리즈": "46파이",
             "북미 CAPEX": "북미CAPEX", "OEM 보상금": "OEM보상금",
             "소형 전지": "소형전지", "유럽 EV": "유럽EV", "북미 EV": "북미EV",
             "중국 경쟁": "중국경쟁", "배터리 판매량": "배터리판매량"}
REGION_STD = {"미국": "북미", "캐나다": "북미", "독일": "유럽", "프랑스": "유럽",
              "영국": "유럽", "이탈리아": "유럽", "스페인": "유럽", "EU": "유럽",
              "일본": "기타", "인도": "기타", "아세안": "기타"}


def canon_company(c):
    return COMPANY_STD.get(c, c)


warnings = []


def warn(rid, msg):
    warnings.append(f"[{rid}] {msg}")


def warnings_for(report_ids):
    report_ids = set(report_ids)
    return [w for w in warnings
            if any(w.startswith(f"[{rid}] ") for rid in report_ids)]


def has_content(value):
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return value is not None and bool(str(value).strip())


def validate(r):
    rid = r.get("report_id", "?")
    for k in ["report_id", "date", "house", "coverage", "report_type", "body"]:
        if not r.get(k):
            warn(rid, f"필수 필드 누락: {k}")
    body = r.get("body")
    if isinstance(body, dict):
        for k in BODY_KEYS:
            if k not in body:
                warn(rid, f"body 필수 키 누락: {k}")
            elif not has_content(body[k]):
                warn(rid, f"body 내용 없음: {k}")
        for k in set(body) - set(BODY_KEYS):
            warn(rid, f"body 비표준 키: {k}")
    elif body is not None:
        warn(rid, "body 형식 오류: 객체(JSON object)가 아님")
    if r.get("opinion") not in OPINIONS:
        warn(rid, f"opinion 비표준: {r.get('opinion')}")
    for e in r.get("estimates", []):
        if e.get("segment_std") == "AMPC":  # 구버전 흔적 교정
            e["segment_std"] = "전사"
            e["metric"] = "AMPC"
        # metric 통제어휘로 통일 (동의어 → 표준어)
        m = e.get("metric")
        if m == "영업이익(AMPC제외)":       # 지표명에 basis가 섞인 표기
            e["metric"], e["ampc_basis"] = "영업이익", "excl"
        elif m in METRIC_STD:
            e["metric"] = METRIC_STD[m]
        elif m is not None and m not in METRICS:
            warn(rid, f"metric 비표준(통제어휘 밖): {m} — METRIC_STD 매핑 추가 검토")
        if e.get("segment_std") not in SEG_STD:
            # 3사 부문이 아닌 밸류체인/소재 등은 '기타'로 강제 (원문 segment 보존)
            warn(rid, f"segment_std '기타'로 강제: {e.get('segment_std')} (segment={e.get('segment')})")
            e["segment_std"] = "기타"
        if e.get("ampc_basis") not in AMPC_BASIS:
            warn(rid, f"ampc_basis 비표준: {e.get('ampc_basis')}")
        if e.get("period") not in PERIODS:
            warn(rid, f"period 비표준: {e.get('period')}")
        if not isinstance(e.get("value"), (int, float)):
            warn(rid, f"value 비숫자: {e.get('value')} ({e.get('metric')})")
        if e.get("unit") not in ("십억원", None):
            warn(rid, f"unit 비표준: {e.get('unit')}")
        if e.get("page") is None:
            warn(rid, f"estimate 원문 페이지 누락: {e.get('metric')} {e.get('fy')} {e.get('period')}")
    for s in r.get("stances", []):
        issue = s.get("issue")
        if issue in ISSUE_STD:
            s["issue"] = ISSUE_STD[issue]
        elif issue not in ISSUES:
            warn(rid, f"stance issue 비표준(통제어휘 밖): {issue}")
        sc = s.get("stance_score")
        if not isinstance(sc, (int, float)) or not -10 <= sc <= 10:
            warn(rid, f"stance_score 범위 밖: {sc}")
        if s.get("page") is None:
            warn(rid, f"stance 원문 페이지 누락: {s.get('issue')}")
    for t in r.get("themes", []) or []:
        theme = t.get("theme")
        if theme in ISSUE_STD:
            t["theme"] = ISSUE_STD[theme]
        elif theme not in ISSUES:
            warn(rid, f"theme 비표준(통제어휘 밖): {theme}")
        d = t.get("direction")
        if not isinstance(d, (int, float)) or not -10 <= d <= 10:
            warn(rid, f"theme direction 범위 밖: {d} ({t.get('theme')})")
    for df in r.get("demand_forecasts", []) or []:
        if df.get("region") in REGION_STD:
            df["basis"] = ((df.get("basis") or "") + f" [원문지역:{df['region']}]").strip()
            df["region"] = REGION_STD[df["region"]]
        if df.get("region") not in ("글로벌", "북미", "유럽", "중국", "한국", "기타"):
            warn(rid, f"demand region 비표준: {df.get('region')}")
        if df.get("application") not in ("EV", "ESS", "합계"):
            warn(rid, f"demand application 비표준: {df.get('application')}")


def yflow(items, keys):
    out = []
    for it in items:
        parts = []
        for k in keys:
            v = it.get(k)
            if isinstance(v, str):
                v = '"' + v.replace('"', "'").replace("\n", " ") + '"'
            elif v is None:
                v = "null"
            parts.append(f"{k}: {v}")
        out.append("  - {" + ", ".join(parts) + "}")
    return "\n".join(out) if out else "  []"


def _bs(x):
    """body 필드 타입 보정: 리스트→개행 결합, None→빈문자열."""
    if x is None:
        return ""
    if isinstance(x, list):
        return "\n".join(str(i) for i in x)
    return str(x)


def render_md(r):
    b = r["body"]
    fm = ["---"]
    for k in ["report_id", "date", "house", "analyst", "coverage", "report_type", "opinion"]:
        v = r.get(k)
        fm.append(f"{k}: {'null' if v is None else v}")
    fm.append(f"target_price: {r.get('target_price') or 'null'}")
    fm.append(f"prev_target_price: {r.get('prev_target_price') or 'null'}")
    fm.append("estimates:")
    fm.append(yflow(r.get("estimates", []),
                    ["company", "segment", "segment_std", "fy", "period",
                     "metric", "value", "unit", "ampc_basis", "page"]))
    fm.append("stances:")
    fm.append(yflow(r.get("stances", []),
                    ["issue", "company", "stance_score", "summary", "page"]))
    if r.get("schema_version"):
        fm.append(f"schema_version: {r['schema_version']}")
    if r.get("demand_forecasts"):
        fm.append("demand_forecasts:")
        fm.append(yflow(r["demand_forecasts"],
                        ["region", "application", "metric", "fy", "value",
                         "value_prev", "unit", "basis", "page"]))
    if r.get("themes"):
        fm.append("themes:")
        fm.append(yflow(r["themes"],
                        ["theme", "direction", "bull", "bear", "summary", "page"]))
    if r.get("industry_views"):
        fm.append("industry_views:")
        fm.append(yflow(r["industry_views"],
                        ["scope", "fy", "metric", "value", "unit",
                         "direction", "summary", "page"]))
    fm.append("key_issues: [" + ", ".join(r.get("key_issues", [])) + "]")
    if r.get("top_picks"):
        fm.append("top_picks: [" + ", ".join(r["top_picks"]) + "]")
    fm.append(f"source_pdf: inbox/{r.get('source_file', '')}")
    fm.append("---")
    body = ["", "## 핵심 요약", _bs(b.get("summary")),
            "", "## 투자의견·목표주가 (도출 근거)", _bs(b.get("valuation")),
            "", "## 사업부문별 손익", _bs(b.get("segment_pl")),
            "", "## 이슈별 코멘트", _bs(b.get("issue_comments")),
            "", "## 리스크 요인", _bs(b.get("risks")),
            "", "## 원문 인용", _bs(b.get("quotes")), ""]
    return "\n".join(fm) + "\n" + "\n".join(body)


def main(check_only=False, force=False, strict_ids=None):
    warnings.clear()
    strict_ids = set(strict_ids or [])
    files = sorted(glob.glob(os.path.join(STAGING, "*.json")))
    reports, actuals_sets = [], []
    for p in files:
        name = os.path.basename(p)
        if name == "manifest.json":
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except json.JSONDecodeError as ex:
            warn(name, f"JSON 파싱 실패: {ex}")
            continue
        if name.startswith("actuals_"):
            actuals_sets.append(d)
        elif name.startswith("viewnarr_") or "report_id" not in d:
            continue  # 파생 산출물(서술 등)은 리포트가 아님
        else:
            stem = os.path.splitext(name)[0]
            if d["report_id"] != stem:
                warn(d["report_id"], f"스테이징 파일명 불일치: {name}")
            reports.append(d)

    # manifest 대조: 누락 파일
    mf = json.load(open(os.path.join(STAGING, "manifest.json"), encoding="utf-8"))
    dup_ids = {m["report_id"] for m in mf if m.get("duplicate_of")}
    if dup_ids:
        reports = [r for r in reports if r["report_id"] not in dup_ids]
        print(f"중복 표시(duplicate_of) 제외: {len(dup_ids)}건")
    mf = [m for m in mf if not m.get("duplicate_of")]
    mf_ids = {m["report_id"] for m in mf}
    have = {r.get("report_id") for r in reports}
    missing = [m["report_id"] for m in mf if m["report_id"] not in have]
    for m in missing:
        warn(m, "스테이징 JSON 없음 (파싱 실패/미완)")
    for rid in sorted(have - mf_ids):
        warn(rid, "manifest 원본 파일 매핑 없음")
    fmap = {m["report_id"]: m["file"] for m in mf}
    for r in reports:
        r["source_file"] = fmap.get(r["report_id"], r.get("source_pdf", ""))
        if r["source_file"] and not os.path.exists(os.path.join(ROOT, "inbox", r["source_file"])):
            warn(r["report_id"], f"원본 PDF 없음: inbox/{r['source_file']}")
        validate(r)

    for rid in sorted(strict_ids - have):
        warn(rid, "엄격 검사 대상 report_id의 스테이징 JSON 없음")

    ids = [r["report_id"] for r in reports]
    if len(ids) != len(set(ids)):
        warn("GLOBAL", "report_id 중복 존재")

    print(f"리포트 {len(reports)}건, actuals 세트 {len(actuals_sets)}건, "
          f"누락 {len(missing)}건, 경고 {len(warnings)}건")
    if strict_ids:
        strict_warnings = warnings_for(strict_ids)
        print(f"엄격 검사 대상 {len(strict_ids)}건, 대상 경고 {len(strict_warnings)}건")
        for w in strict_warnings:
            print(" ", w)
        return 1 if missing or strict_warnings else 0
    if check_only:
        for w in warnings:
            print(" ", w)
        return 1 if missing else 0

    # --- 안전장치: 재빌드가 기존 DB를 축소시키면 중단 ---
    # 이 스크립트는 .staging 을 유일한 소스로 삼아 index/ 를 전량 덮어쓴다.
    # staging 이 비어 있거나 일부만 있는 클론에서 실행하면 DB가 지워지므로,
    # 리포트 수가 줄어드는 재빌드는 기본적으로 거부한다. (의도적 삭제 시 --force)
    prev_path = os.path.join(ROOT, "index", "reports.jsonl")
    if os.path.exists(prev_path):
        with open(prev_path, encoding="utf-8") as f:
            previous = [json.loads(line) for line in f if line.strip()]
        prev_n = len(previous)
        if not force and len(reports) < prev_n:
            print(f"\n[중단] 재빌드가 DB를 축소시킵니다: 기존 {prev_n}건 → staging {len(reports)}건")
            print(f"  .staging/*.json 이 {len(reports)}개만 있습니다. 클론에 staging 이 없거나 일부만 받은 상태일 수 있습니다.")
            print("  index/ 와 reports/ 를 덮어쓰지 않고 종료합니다.")
            print("  의도적으로 리포트를 줄이는 경우에만: python3 tools/build_indexes.py --force")
            return 2
        new_ids = have - {r["report_id"] for r in previous}
        new_warnings = warnings_for(new_ids)
        if new_warnings:
            print(f"\n[중단] 신규 리포트 엄격 검증 실패: {len(new_ids)}건 중 경고 {len(new_warnings)}건")
            for w in new_warnings:
                print(" ", w)
            print("  index/ 와 reports/ 를 덮어쓰지 않고 종료합니다.")
            print("  각 신규 ID를 --check-id로 검사해 대상 경고를 0건으로 만든 뒤 재시도하세요.")
            return 3

    # --- MD ---
    for r in reports:
        year = r["date"][:4]
        d = os.path.join(ROOT, "reports", year)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, r["report_id"] + ".md"), "w", encoding="utf-8") as f:
            f.write(render_md(r))

    idx = os.path.join(ROOT, "index")

    # --- reports.jsonl ---
    with open(os.path.join(idx, "reports.jsonl"), "w", encoding="utf-8") as f:
        for r in sorted(reports, key=lambda x: x["date"]):
            row = {k: r.get(k) for k in
                   ["report_id", "date", "house", "analyst", "coverage",
                    "report_type", "opinion", "target_price",
                    "prev_target_price", "key_issues", "top_picks"]}
            row["summary"] = _bs(r["body"].get("summary"))
            row["source_pdf"] = "inbox/" + r["source_file"]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # --- estimates.csv ---
    with open(os.path.join(idx, "estimates.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "date", "house", "company", "segment", "segment_std",
                    "fy", "period", "metric", "value", "unit", "ampc_basis", "source_page"])
        for r in sorted(reports, key=lambda x: x["date"]):
            for e in r.get("estimates", []):
                w.writerow([r["report_id"], r["date"], r["house"], canon_company(e.get("company")),
                            e.get("segment"), e.get("segment_std"), e.get("fy"),
                            e.get("period"), e.get("metric"), e.get("value"),
                            e.get("unit"), e.get("ampc_basis"), e.get("page")])

    # --- stances.csv ---
    with open(os.path.join(idx, "stances.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "date", "house", "company", "issue",
                    "stance_score", "summary", "source_page"])
        for r in sorted(reports, key=lambda x: x["date"]):
            for s in r.get("stances", []):
                w.writerow([r["report_id"], r["date"], r["house"], canon_company(s.get("company")),
                            s.get("issue"), s.get("stance_score"),
                            s.get("summary"), s.get("page")])

    # --- industry_views.csv ---
    with open(os.path.join(idx, "industry_views.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "date", "house", "scope", "fy", "metric",
                    "value", "unit", "direction", "summary", "source_page"])
        for r in sorted(reports, key=lambda x: x["date"]):
            for v in r.get("industry_views", []) or []:
                w.writerow([r["report_id"], r["date"], r["house"], v.get("scope"),
                            v.get("fy"), v.get("metric"), v.get("value"),
                            v.get("unit"), v.get("direction"),
                            v.get("summary"), v.get("page")])

    # --- demand_forecasts.csv / themes.csv (산업 v3) ---
    # series_class/series_label/scope_note: 비교가능성 큐레이션 (demand_curation.py, v8)
    from demand_curation import classify
    with open(os.path.join(idx, "demand_forecasts.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "date", "house", "region", "application", "metric",
                    "fy", "value", "value_prev", "unit", "basis", "source_page",
                    "series_class", "series_label", "scope_note"])
        for r in sorted(reports, key=lambda x: x["date"]):
            for d in r.get("demand_forecasts", []) or []:
                c = classify(r["report_id"], d.get("region"), d.get("application"),
                             d.get("metric"), d.get("unit"), d.get("basis"))
                w.writerow([r["report_id"], r["date"], r["house"], d.get("region"),
                            d.get("application"), d.get("metric"), d.get("fy"),
                            d.get("value"), d.get("value_prev"), d.get("unit"),
                            d.get("basis"), d.get("page"),
                            c["cls"], c["label"], c["scope"]])
    with open(os.path.join(idx, "themes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["report_id", "date", "house", "theme", "direction",
                    "bull", "bear", "summary", "source_page"])
        for r in sorted(reports, key=lambda x: x["date"]):
            for t in r.get("themes", []) or []:
                w.writerow([r["report_id"], r["date"], r["house"], t.get("theme"),
                            t.get("direction"), t.get("bull"), t.get("bear"),
                            t.get("summary"), t.get("page")])

    # --- actuals.csv + drivers.csv ---
    with open(os.path.join(idx, "actuals.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "fy", "period", "segment", "segment_std", "metric",
                    "value", "unit", "ampc_basis", "source_file", "source_page"])
        for a in actuals_sets:
            for row in a.get("actuals", []):
                w.writerow([a["company"], row.get("fy"), row.get("period"),
                            row.get("segment"), row.get("segment_std"),
                            row.get("metric"), row.get("value"), row.get("unit"),
                            row.get("ampc_basis", "na"),
                            row.get("source_file"), row.get("page")])
    with open(os.path.join(idx, "drivers.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "fy", "period", "segment_std", "summary",
                    "source_file", "source_page"])
        for a in actuals_sets:
            for row in a.get("drivers", []):
                w.writerow([a["company"], row.get("fy"), row.get("period"),
                            row.get("segment_std"), row.get("summary"),
                            row.get("source_file"), row.get("page")])

    print("렌더 완료. 경고 목록:")
    for w_ in warnings:
        print(" ", w_)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="스테이징 JSON에서 표준 MD와 인덱스를 생성합니다.")
    parser.add_argument("--check", action="store_true", help="검증만 수행하고 파일을 쓰지 않습니다.")
    parser.add_argument("--check-id", action="append", default=[], metavar="REPORT_ID",
                        help="지정 report_id만 엄격 검증합니다. 여러 번 지정할 수 있습니다.")
    parser.add_argument("--force", action="store_true", help="DB 축소 안전장치를 무시합니다.")
    args = parser.parse_args()
    sys.exit(main(args.check or bool(args.check_id), args.force, args.check_id))
