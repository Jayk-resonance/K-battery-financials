#!/usr/bin/env python3
"""인덱스 -> 대시보드 데이터셋 (projects/dashboard/data.json).

기능별 블록:
  f1_quarterly   분기별 3사 재무 비교 (부문 포함, QoQ/YoY, 드라이버 설명)
  f2_stance      이슈별 3사 스탠스 매트릭스
  f3_views       증권사별 View 변화 (목표주가/의견 시계열)
  f4_accuracy    컨센서스 적중률 (1Q26 + FY2025 빈티지)
  f5_outliers    이견/아웃라이어 탐지
  f6_dotplots    FOMC식 점도표 (3사 영업이익 / 산업 지역별)

정규화: NORMALIZATION.md 준수. OP_incl = excl + AMPC(동일 키) 파생.
"""
import json, csv, os, statistics as st, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "projects", "dashboard")
os.makedirs(OUT, exist_ok=True)

COMPANIES = ["LGES", "삼성SDI", "SK온"]
ANNOUNCE = {("LGES", 2026, "1Q"): "2026-04-08", ("삼성SDI", 2026, "1Q"): "2026-04-28",
            ("SK온", 2026, "1Q"): "2026-05-13"}

est = list(csv.DictReader(open(f"{IDX}/estimates.csv", encoding="utf-8")))
stances = list(csv.DictReader(open(f"{IDX}/stances.csv", encoding="utf-8")))
actuals = list(csv.DictReader(open(f"{IDX}/actuals.csv", encoding="utf-8")))
iviews = list(csv.DictReader(open(f"{IDX}/industry_views.csv", encoding="utf-8")))
reports = [json.loads(l) for l in open(f"{IDX}/reports.jsonl", encoding="utf-8")]
drivers = list(csv.DictReader(open(f"{IDX}/drivers.csv", encoding="utf-8")))

CUR = os.path.join(OUT, "narratives.json")  # 큐레이션 내러티브 (수기)
narratives = json.load(open(CUR, encoding="utf-8")) if os.path.exists(CUR) else {}
# 이슈별 긍정/부정 요약 (생성물, issue|company 키). 하우스 구성이 바뀌면 재생성 필요.
ISUM = os.path.join(OUT, "issue_summaries.json")
issue_summaries = json.load(open(ISUM, encoding="utf-8")) if os.path.exists(ISUM) else {}

for e in est:
    e["value"] = float(e["value"]) if e["value"] else None

# 실적 확정 기간의 영업이익 ampc_basis 자동 교정 (v9).
# 리포트가 표기한 basis(incl_unknown/na 포함)와 무관하게, 숫자가 실적의
# incl/excl 어느 쪽과 일치하는지로 바로잡는다 — 점도표·적중률 오염 방지.
# 새 실적이 확정되면 여기에 한 줄 추가한다.
KNOWN_OP_BASIS = {
    ("LGES", "2025", "FY"): {"incl": 1346.0, "excl": -301.0},       # AMPC 1,647
    ("삼성SDI", "2025", "FY"): {"incl": -1722.4, "excl": -1998.0},   # AMPC 275
    ("LGES", "2026", "1Q"): {"incl": -207.8, "excl": -397.6},       # AMPC 190
    ("삼성SDI", "2026", "1Q"): {"incl": -155.6},                     # 분기 AMPC 실적 미공시 → excl 대조 불가
    ("SK온", "2026", "1Q"): {"incl": -349.2},
}
_TOL = 2.0  # 십억원
# 해당 기간의 실적 발표일 — 이후 발간 리포트의 불일치 값은 기준 검증 불가로 점도표 제외
KNOWN_ANNOUNCE = {("LGES", "2025", "FY"): "2026-02-01", ("삼성SDI", "2025", "FY"): "2026-02-01",
                  ("LGES", "2026", "1Q"): "2026-04-08", ("삼성SDI", "2026", "1Q"): "2026-04-28",
                  ("SK온", "2026", "1Q"): "2026-05-13"}


def known_mismatch(comp, fy, period, rdate, op):
    """실적 발표 후 리포트인데 incl 실적과 불일치 → 기준 불명(예: 미공시 AMPC 차감치)."""
    k = KNOWN_OP_BASIS.get((comp, str(fy), period))
    ad = KNOWN_ANNOUNCE.get((comp, str(fy), period))
    return (k and ad and rdate >= ad and "incl" in k
            and abs(op - k["incl"]) > _TOL)


for e in est:
    if e["metric"] != "영업이익" or e["value"] is None \
       or e["segment_std"] not in ("전사", "배터리합계"):
        continue
    k = KNOWN_OP_BASIS.get((e["company"], e["fy"], e["period"]))
    if not k:
        continue
    if "incl" in k and abs(e["value"] - k["incl"]) <= _TOL:
        e["ampc_basis"] = "incl"
    elif "excl" in k and abs(e["value"] - k["excl"]) <= _TOL:
        e["ampc_basis"] = "excl"


def op_incl(rows_one_report, company, seg, fy, period):
    """한 리포트 내에서 AMPC 포함 영업이익 도출 (기준 통일)."""
    sel = [r for r in rows_one_report if r["company"] == company
           and r["segment_std"] == seg and r["fy"] == str(fy) and r["period"] == period]
    op = {r["ampc_basis"]: r["value"] for r in sel if r["metric"] == "영업이익"}
    ampc = next((r["value"] for r in sel if r["metric"] == "AMPC"), None)
    if ampc is None:  # 전사 AMPC로 폴백 (seg=전사일 때만 의미)
        ampc = next((r["value"] for r in rows_one_report
                     if r["company"] == company and r["fy"] == str(fy)
                     and r["period"] == period and r["metric"] == "AMPC"
                     and r["segment_std"] == "전사"), None)
    if "incl" in op:
        return op["incl"], "incl"
    if "excl" in op and ampc is not None:
        return op["excl"] + ampc, "derived(excl+AMPC)"
    if "incl_unknown" in op:
        return op["incl_unknown"], "incl_unknown"
    if "excl" in op:
        return op["excl"], "excl_only"
    if "na" in op:
        return op["na"], "na"
    return None, None


by_report = collections.defaultdict(list)
for e in est:
    by_report[e["report_id"]].append(e)
rmeta = {r["report_id"]: r for r in reports}

# ---------- F1: 분기별 실적 비교 ----------
def actual_grid():
    grid = collections.defaultdict(dict)  # (company,fy,period) -> {seg/metric: val}
    for a in actuals:
        if a["period"] == "FY":
            continue
        k = (a["company"], int(a["fy"]), a["period"])
        grid[k][f"{a['segment_std']}|{a['metric']}|{a.get('ampc_basis','na')}"] = float(a["value"])
    return grid

# SK온 분기 실적: 발간일 기준 이미 발표된 분기의 애널리스트 인용값 중앙값
def skon_quarters():
    out = {}
    for fy, period, cutoff in [(2025,"1Q","2025-04-30"),(2025,"2Q","2025-08-01"),
                               (2025,"3Q","2025-11-01"),(2025,"4Q","2026-02-01"),
                               (2026,"1Q","2026-05-01")]:
        for metric in ["매출","영업이익"]:
            vals = [e["value"] for e in est if e["company"]=="SK온"
                    and e["segment_std"]=="배터리합계" and e["fy"]==str(fy)
                    and e["period"]==period and e["metric"]==metric
                    and e["date"] >= cutoff and e["value"] is not None]
            if vals:
                out[f"{fy}|{period}|{metric}"] = {"value": round(st.median(vals),1),
                                                  "n_sources": len(vals), "method": "애널리스트 인용 중앙값"}
    return out

f1 = {"actuals_grid": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in actual_grid().items()},
      "skon_quarters": skon_quarters(),
      "company_drivers": [dict(d) for d in drivers],
      "narratives": narratives.get("f1", {})}

# ---------- F2: 이슈별 스탠스 매트릭스 ----------
ISSUE_ALIAS = {"배터리판매량":"판매량","북미EV":"북미수요","유럽EV":"유럽수요","북미ESS":"ESS"}
mat = collections.defaultdict(list)
for s in stances:
    comp = s["company"]
    rm_s = rmeta.get(s["report_id"])
    if comp not in COMPANIES or not rm_s or rm_s.get("report_type") != "기업":
        continue
    issue = ISSUE_ALIAS.get(s["issue"], s["issue"])
    # 북미 증설은 ESS/EV 내용이 혼재 → 요약 키워드로 분리(ESS 언급 시 ESS, 아니면 EV)
    if issue == "북미CAPEX":
        issue = "북미증설(ESS)" if "ESS" in (s["summary"] or "") else "북미증설(EV)"
    # 판매량은 지역 EV 수요와 사실상 동일 축 → 유럽 신호면 유럽수요, 그 외(북미·글로벌·국내)는 북미수요로 통합
    if issue == "판매량":
        su = s["summary"] or ""
        eu = any(k in su for k in ["유럽", "EU", "벤츠", "폭스바겐", "BMW"])
        na = any(k in su for k in ["북미", "미국", "GM", "포드", "스텔란티스", "Rivian", "Stellantis"])
        issue = "유럽수요" if (eu and not na) else "북미수요"
    mat[(issue, comp)].append({"house": s["house"], "date": s["date"],
                               "score": float(s["stance_score"]) if s["stance_score"] else 0,
                               "summary": s["summary"], "report_id": s["report_id"]})
f2 = []
for (issue, comp), items in mat.items():
    items.sort(key=lambda x: x["date"])
    latest = {}
    for i in items:  # 하우스당 최신 1건 (1하우스 1표)
        cur = latest.get(i["house"])
        if not cur or i["date"] > cur["date"]:
            latest[i["house"]] = i
    lv = [i["score"] for i in latest.values()]
    # 긍정/부정 요약 부착 + staleness 검사 (하우스 구성이 바뀌면 경고)
    summ = issue_summaries.get(f"{issue}|{comp}")
    if summ:
        cur_pos = sorted(i["house"] for i in latest.values() if i["score"] > 0)
        cur_neg = sorted(i["house"] for i in latest.values() if i["score"] < 0)
        if cur_pos != summ.get("pos_houses") or cur_neg != summ.get("neg_houses"):
            print(f"  [STALE] 요약 재생성 필요: {issue}|{comp} (하우스 구성 변경)")
    f2.append({"issue": issue, "company": comp,
               "median_recent": st.median(lv), "mean_recent": round(st.mean(lv), 1),
               "n_houses": len(lv), "n": len(items), "items": items,
               "summary": {"pos": summ["pos"], "neg": summ["neg"]} if summ else None})

# ---------- F3: 증권사별 View 변화 ----------
f3 = collections.defaultdict(list)
for r in sorted(reports, key=lambda x: x["date"]):
    if r["coverage"] not in COMPANIES:
        continue
    srows = [s for s in stances if s["report_id"] == r["report_id"]]
    avg = round(st.mean([float(s["stance_score"]) for s in srows]), 2) if srows else None
    f3[f"{r['house']}|{r['coverage']}"].append(
        {"date": r["date"], "opinion": r["opinion"], "target_price": r["target_price"],
         "avg_stance": avg, "report_id": r["report_id"], "summary": r["summary"][:120]})
f3 = dict(f3)

# ---------- F4: 컨센서스 적중률 ----------
f4 = {"events": []}
for (comp, fy, period), adate in ANNOUNCE.items():
    seg_t = "배터리합계" if comp == "SK온" else "전사"
    act_rows = [a for a in actuals if a["company"] == comp and a["fy"] == str(fy)
                and a["period"] == period and a["segment_std"] == seg_t]
    act = {}
    for a in act_rows:
        act.setdefault(a["metric"], float(a["value"]))
    if not act:
        continue
    preds = []
    for rid, rows in by_report.items():
        rm = rmeta.get(rid)
        if not rm or rm["date"] >= adate or rm["coverage"] != comp:
            continue
        if rm["date"] < "2026-02-01":
            continue  # 직전 프리뷰 시즌만
        op, basis = op_incl(rows, comp, seg_t, fy, period)
        rev = next((r["value"] for r in rows if r["company"] == comp
                    and r["segment_std"] == seg_t and r["fy"] == str(fy)
                    and r["period"] == period and r["metric"] == "매출"), None)
        if op is None and rev is None:
            continue
        e = {"house": rm["house"], "date": rm["date"], "report_id": rid,
             "op_est": op, "op_basis": basis, "rev_est": rev}
        if op is not None and act.get("영업이익") is not None:
            e["op_err"] = round(op - act["영업이익"], 1)
        if rev is not None and act.get("매출") is not None:
            e["rev_err_pct"] = round((rev - act["매출"]) / act["매출"] * 100, 1)
        preds.append(e)
    # 이벤트 결론: 프리뷰 컨센서스(중앙값) 대비 실제가 얼마나 벗어났나
    ops = [p["op_est"] for p in preds if p["op_est"] is not None]
    med = round(st.median(ops), 1) if ops else None
    verdict = diff = None
    if med is not None and act.get("영업이익") is not None:
        diff = round(act["영업이익"] - med, 1)
        thr = max(abs(med) * 0.15, 30)  # 중앙값의 15% 또는 300억원 중 큰 쪽
        verdict = ("어닝 서프라이즈" if diff > thr
                   else "어닝 쇼크" if diff < -thr else "컨센서스 부합")
    f4["events"].append({"company": comp, "fy": fy, "period": period,
                         "announce_date": adate, "actual": act, "preds": preds,
                         "consensus_median": med, "diff": diff, "verdict": verdict})

# FY2025 빈티지 적중률 (2023~25년 리포트의 FY2025 전망 vs 실제)
ACT_FY25 = {"LGES": {"매출": 23672, "영업이익": 1346}, "삼성SDI": {"매출": 13267, "영업이익": -1722}}
vint = []
for rid, rows in by_report.items():
    rm = rmeta.get(rid)
    if not rm or rm["date"] >= "2025-10-01":
        continue
    for comp in ["LGES", "삼성SDI"]:
        op, basis = op_incl(rows, comp, "전사", 2025, "FY")
        if op is None:
            continue
        vint.append({"house": rm["house"], "date": rm["date"], "report_id": rid,
                     "src_type": rm["report_type"],
                     "company": comp, "op_est": op, "op_basis": basis,
                     "op_actual": ACT_FY25[comp]["영업이익"],
                     "op_err": round(op - ACT_FY25[comp]["영업이익"], 1)})
f4["fy2025_vintage"] = sorted(vint, key=lambda x: x["date"])

# ---------- F5: 아웃라이어 ----------
# 대상 기간 자동 롤링: (1) 최신 실적 발표 분기의 다음 분기 (2) 분석년도.
# 분석년도는 3Q 실적 발표 전까지는 당해, 발표 후에는 다음 해.
_QS = ["1Q", "2Q", "3Q", "4Q"]
_last_fy, _last_q = sorted(((fy, q) for (_c, fy, q) in ANNOUNCE),
                           key=lambda k: (k[0], _QS.index(k[1])))[-1]
if _last_q == "4Q":
    _nq_fy, _nq = _last_fy + 1, "1Q"
else:
    _nq_fy, _nq = _last_fy, _QS[_QS.index(_last_q) + 1]
_ana_fy = _last_fy if _QS.index(_last_q) < 2 else _last_fy + 1
F5_TARGETS = [(_nq_fy, _nq), (_ana_fy, "FY")]

f5 = {"estimate_outliers": [], "stance_outliers": []}
for comp, seg in [("LGES","전사"),("삼성SDI","전사"),("SK온","배터리합계")]:
    for fy, period in F5_TARGETS:
        latest = {}
        for rid, rows in by_report.items():
            rm = rmeta.get(rid)
            if not rm or rm["coverage"] != comp or rm["date"] < "2026-03-01":
                continue
            op, basis = op_incl(rows, comp, seg, fy, period)
            if op is None or basis in ("excl_only",):
                continue
            cur = latest.get(rm["house"])
            if not cur or rm["date"] > cur["date"]:
                latest[rm["house"]] = {"house": rm["house"], "date": rm["date"],
                                       "op": op, "basis": basis, "report_id": rid}
        vals = [v["op"] for v in latest.values()]
        if len(vals) >= 3:
            med = st.median(vals)
            for v in latest.values():
                v["dev_from_median"] = round(v["op"] - med, 1)
            ranked = sorted(latest.values(), key=lambda x: -abs(x["dev_from_median"]))
            # 하이라이트 3곳: 최비관·최낙관 필수 + 나머지 중 최대 이탈
            lo_h = min(latest.values(), key=lambda x: x["op"])
            hi_h = max(latest.values(), key=lambda x: x["op"])
            lo_h["tag"] = "최저 추정"; hi_h["tag"] = "최고 추정"
            picks, seen = [], set()
            for h in [lo_h, hi_h] + ranked:
                if h["house"] not in seen:
                    picks.append(h); seen.add(h["house"])
                if len(picks) == 3:
                    break
            for v in picks:
                v["summary"] = (rmeta.get(v["report_id"], {}).get("summary") or "")
                # 논조 근거: 해당 리포트의 이슈별 스탠스(확신도 강한 순 상위 4개)
                v["stances"] = sorted(
                    [{"issue": ISSUE_ALIAS.get(s["issue"], s["issue"]),
                      "score": float(s["stance_score"]) if s["stance_score"] else 0,
                      "summary": s["summary"]}
                     for s in stances if s["report_id"] == v["report_id"]
                     and s["company"] == comp],
                    key=lambda x: -abs(x["score"]))[:4]
                v["pick"] = True
            f5["estimate_outliers"].append(
                {"company": comp, "fy": fy, "period": period, "median": med,
                 "n_houses": len(vals), "houses": ranked})
for row in f2:
    if row["n"] >= 3:
        scores = [i["score"] for i in row["items"] if i["date"] >= "2026-01-01"]
        if len(scores) >= 3:
            med = st.median(scores)
            outl = [i for i in row["items"] if i["date"] >= "2026-01-01"
                    and abs(i["score"] - med) >= 5]
            if outl:
                f5["stance_outliers"].append({"issue": row["issue"], "company": row["company"],
                                              "median": med, "outliers": outl})

# ---------- F6: 점도표 ----------
F6_ACTUALS = {"LGES": {"2025": 1346.0}, "삼성SDI": {"2025": -1722.4}, "SK온": {"2025": -931.9}}
f6 = {"op_dots": [], "industry_dots": [], "fy_actuals": F6_ACTUALS}
for comp, seg in [("LGES","전사"),("삼성SDI","전사"),("SK온","배터리합계")]:
    dots = []
    for rid, rows in by_report.items():
        rm = rmeta.get(rid)
        if not rm or rm.get("report_type") != "기업":
            continue
        for fy in [2025, 2026, 2027, 2028]:
            op, basis = op_incl(rows, comp, seg, fy, "FY")
            # excl_only/na는 AMPC 포함으로 환산 불가 → 점도표 제외 (기준 오염 방지)
            if op is not None and basis not in ("excl_only", "na") \
               and not known_mismatch(comp, fy, "FY", rm["date"], op):
                dots.append({"house": rm["house"], "report_date": rm["date"],
                             "fy": fy, "op": op, "basis": basis, "report_id": rid})
    f6["op_dots"].append({"company": comp, "segment": seg, "dots": dots})

# 2026년 분기별 점도표 (+ 발표된 분기의 실적선)
QFY = 2026
q_act = {}
for a in actuals:
    seg_t = "배터리합계" if a["company"] == "SK온" else "전사"
    if (a["company"] in COMPANIES and a["fy"] == str(QFY) and a["period"] in _QS
            and a["metric"] == "영업이익" and a["segment_std"] == seg_t):
        q_act.setdefault(a["company"], {})[a["period"]] = float(a["value"])
f6["q_fy"] = QFY
f6["q_actuals"] = q_act
f6["q_announce"] = {c: d for (c, fy, q), d in ANNOUNCE.items() if fy == QFY}
f6["op_dots_q"] = []
for comp, seg in [("LGES","전사"),("삼성SDI","전사"),("SK온","배터리합계")]:
    dots = []
    for rid, rows in by_report.items():
        rm = rmeta.get(rid)
        if not rm or rm.get("report_type") != "기업":
            continue
        for q in _QS:
            op, basis = op_incl(rows, comp, seg, QFY, q)
            if op is not None and basis not in ("excl_only", "na") \
               and not known_mismatch(comp, QFY, q, rm["date"], op):
                dots.append({"house": rm["house"], "report_date": rm["date"],
                             "q": q, "op": op, "basis": basis, "report_id": rid})
    f6["op_dots_q"].append({"company": comp, "segment": seg, "dots": dots})
for v in iviews:
    if v["direction"]:
        f6["industry_dots"].append({"house": v["house"], "date": v["date"],
                                    "scope": v["scope"], "fy": v["fy"],
                                    "direction": float(v["direction"]),
                                    "value": v["value"], "unit": v["unit"],
                                    "summary": v["summary"], "report_id": v["report_id"]})


# ---------- F1: 전사 분기 컨센서스 (미발표 분기 점선 연장용, v10) ----------
# 영업이익 = 분기별 점도표(하우스별 최신)의 중앙값과 동일 계산.
# 매출 = 하우스별 최신 리포트의 매출 중앙값 (LGES는 excl 우선, incl-AMPC 파생 폴백).
est_quarters = {}
for comp, seg in [("LGES", "전사"), ("삼성SDI", "전사"), ("SK온", "배터리합계")]:
    grp = next(g for g in f6["op_dots_q"] if g["company"] == comp)
    per_comp = {}
    for q in _QS:
        if q in q_act.get(comp, {}):
            continue  # 실적 있는 분기는 제외
        seen = {}
        for d in sorted(grp["dots"], key=lambda x: x["report_date"], reverse=True):
            if d["q"] == q and d["house"] not in seen:
                seen[d["house"]] = d["op"]
        rev_seen = {}
        for rid, rows in by_report.items():
            rm = rmeta.get(rid)
            if not rm or rm["coverage"] != comp or rm["date"] < "2026-03-01":
                continue
            sel_r = [r for r in rows if r["company"] == comp and r["segment_std"] == seg
                     and r["fy"] == str(QFY) and r["period"] == q and r["value"] is not None]
            rv = {r["ampc_basis"]: r["value"] for r in sel_r if r["metric"] == "매출"}
            ampc = next((r["value"] for r in sel_r if r["metric"] == "AMPC"), None)
            v = rv.get("excl")
            if v is None and comp == "LGES" and "incl" in rv and ampc is not None:
                v = rv["incl"] - ampc
            if v is None:
                v = rv.get("na", rv.get("incl", rv.get("incl_unknown")))
            if v is not None:
                cur = rev_seen.get(rm["house"])
                if not cur or rm["date"] > cur[0]:
                    rev_seen[rm["house"]] = (rm["date"], v)
        entry = {}
        if seen:
            entry["영업이익"] = round(st.median(seen.values()), 1)
            entry["영업이익_n"] = len(seen)
        if rev_seen:
            entry["매출"] = round(st.median(v for _, v in rev_seen.values()), 1)
            entry["매출_n"] = len(rev_seen)
        if entry:
            per_comp[f"{QFY}|{q}"] = entry
    est_quarters[comp] = per_comp

# ---------- F1-SEG: 사업부문별 증권사 컨센서스 (분기·연간) ----------
# 규칙: (1) 부문 영업이익은 excl-AMPC 행만 (분리 불가 리포트는 제외, 억지 배분 금지)
#       (2) 하우스당 그 기간에 대한 최신 리포트 1건만 (1하우스 1표)
#       (3) 레벨 혼합 금지 — EV/ESS 분리 하우스와 중대형 합본 하우스는 각자 레벨에서만
#       (4) 중앙값 기본 + 평균 병기 + n 필수
SEG_LEVELS = ["소형", "EV", "ESS", "중대형", "전자재료", "배터리합계", "전사"]
PERIODS_SEG = [(2025,"1Q"),(2025,"2Q"),(2025,"3Q"),(2025,"4Q"),
               (2026,"1Q"),(2026,"2Q"),(2026,"3Q"),(2026,"4Q"),
               (2026,"FY"),(2027,"FY")]

def seg_consensus():
    # 롤업 파생: 하우스가 같은 리포트에서 EV+ESS(excl)를 모두 주면 중대형(derived) 후보
    derived_mid = collections.defaultdict(dict)  # (comp,fy,period,metric) -> house -> row
    tmp = collections.defaultdict(dict)
    for e in est:
        rm = rmeta.get(e["report_id"])
        if not rm or rm.get("report_type") != "기업" or e["value"] is None:
            continue
        if e["segment_std"] in ("EV", "ESS") and e["metric"] in ("매출", "영업이익"):
            basis_ok = e["ampc_basis"] == "excl" if e["metric"] == "영업이익" else e["ampc_basis"] in ("excl", "na")
            if basis_ok:
                tmp[(e["report_id"], e["company"], e["fy"], e["period"], e["metric"])][e["segment_std"]] = e
    for (rid, comp, fy, period, metric), segs in tmp.items():
        if "EV" in segs and "ESS" in segs:
            rm = rmeta[rid]
            cur = derived_mid.get((comp, fy, period, metric), {}).get(rm["house"])
            if not cur or rm["date"] > cur["date"]:
                derived_mid.setdefault((comp, fy, period, metric), {})[rm["house"]] = {
                    "house": rm["house"], "date": rm["date"],
                    "value": round(segs["EV"]["value"] + segs["ESS"]["value"], 1),
                    "basis": "derived(EV+ESS)", "report_id": rid,
                    "page": segs["EV"].get("source_page")}
    out = {}
    for comp in COMPANIES:
        cout = {}
        for fy, period in PERIODS_SEG:
            pout = {}
            for seg in SEG_LEVELS:
                sout = {}
                for metric, basis_ok in [("매출", {"excl","na"}), ("영업이익", {"excl"}),
                                          ("영업이익(incl)", {"incl"}), ("AMPC", {"na","excl","incl","incl_unknown"})]:
                    m = "영업이익" if metric == "영업이익(incl)" else metric
                    latest = {}
                    for e in est:
                        if (e["company"] != comp or e["segment_std"] != seg
                                or e["fy"] != str(fy) or e["period"] != period
                                or e["metric"] != m or e["value"] is None):
                            continue
                        if e["ampc_basis"] not in basis_ok:
                            continue
                        rm = rmeta.get(e["report_id"])
                        if not rm or rm.get("report_type") != "기업":
                            continue
                        cur = latest.get(e["house"])
                        if not cur or e["date"] > cur["date"]:
                            latest[e["house"]] = {"house": e["house"], "date": e["date"],
                                                  "value": e["value"], "basis": e["ampc_basis"],
                                                  "report_id": e["report_id"], "page": e["source_page"]}
                    if seg == "중대형" and metric in ("매출", "영업이익"):
                        for h, v in derived_mid.get((comp, str(fy), period, metric), {}).items():
                            if h not in latest:
                                latest[h] = v
                    if len(latest) >= 2:
                        vals = [v["value"] for v in latest.values()]
                        sout[metric] = {"median": round(st.median(vals), 1),
                                        "mean": round(st.mean(vals), 1), "n": len(vals),
                                        "houses": sorted(latest.values(), key=lambda x: x["value"])}
                if sout:
                    pout[seg] = sout
            if pout:
                cout[f"{fy}|{period}"] = pout
        out[comp] = cout
    return out

f1["seg_consensus"] = seg_consensus()
f1["est_quarters"] = est_quarters

# ---------- F3: View 서술 병합 ----------
import glob as _glob
vn = {}
for _p in _glob.glob(os.path.join(ROOT, ".staging", "viewnarr_*.json")):
    try:
        d = json.load(open(_p, encoding="utf-8"))
        for it in d.get("items", []):
            vn[f"{d['house']}|{it['company']}"] = it["narrative"]
    except Exception:
        pass
f3_narr = vn

# ---------- F7: 산업 View (산업리포트 전용) ----------
ind_reports = [r for r in reports if r.get("report_type") == "산업"]
ind_ids = {r["report_id"] for r in ind_reports}
regimes, ind_meta = [], {}
for _p in _glob.glob(os.path.join(ROOT, ".staging", "*.json")):
    name = os.path.basename(_p)
    if name.startswith(("actuals_", "viewnarr_", "manifest")):
        continue
    try:
        d = json.load(open(_p, encoding="utf-8"))
    except Exception:
        continue
    if d.get("report_id") in ind_ids:
        ind_meta[d["report_id"]] = d
        mr = d.get("market_regime") or {}
        regimes.append({"report_id": d["report_id"], "date": d["date"], "house": d["house"],
                        "phase": mr.get("phase"), "summary": mr.get("summary"),
                        "sector_rating": d.get("sector_rating"),
                        "top_picks": d.get("top_picks") or [],
                        "title_summary": (d.get("body") or {}).get("summary", "")[:180]})
regimes.sort(key=lambda x: x["date"])

# v3: demand_forecasts / themes 인덱스에서 로드 (없으면 빈 리스트)
def _load(name):
    fp = f"{IDX}/{name}"
    return list(csv.DictReader(open(fp, encoding="utf-8"))) if os.path.exists(fp) else []

demand_rows = []
for d in _load("demand_forecasts.csv"):
    if d["value"] in ("", None):
        continue
    # 대시보드는 수요량·침투율만 사용 (성장률/실적치/판매대수 등은 CSV에 유지, 표시 제외)
    if d["metric"] not in ("수요량", "침투율"):
        continue
    demand_rows.append({"house": d["house"], "date": d["date"], "region": d["region"],
                        "application": d["application"], "metric": d["metric"],
                        "fy": int(d["fy"]) if d["fy"] else None, "value": float(d["value"]),
                        "value_prev": float(d["value_prev"]) if d["value_prev"] else None,
                        "unit": d["unit"], "basis": d["basis"], "report_id": d["report_id"],
                        "cls": d.get("series_class") or "시장전체",
                        "sk": d["report_id"] + "|" + (d.get("series_label") or d["basis"] or ""),
                        "scope": d.get("scope_note") or None})
theme_rows = []
for t in _load("themes.csv"):
    if not t["direction"]:
        continue
    theme_rows.append({"house": t["house"], "date": t["date"], "theme": t["theme"],
                       "direction": float(t["direction"]), "bull": t["bull"] or None,
                       "bear": t["bear"] or None, "summary": t["summary"],
                       "report_id": t["report_id"]})
f7 = {"regimes": regimes, "demand": demand_rows, "themes": theme_rows,
      "n_reports": len(ind_reports)}

# 원본 PDF 총 페이지 수 (분석 볼륨 지표). pdfinfo·원본 PDF가 있으면 계수, 없으면 None.
def total_pages():
    import subprocess as sp, re as _re
    tot = 0
    for r in reports:
        path = os.path.join(ROOT, r.get("source_pdf", "")) if r.get("source_pdf") else ""
        if not path or not os.path.exists(path):
            return None  # 원본 PDF가 없으면(영속 DB만 존재) 페이지 지표 생략
        try:
            out = sp.run(["pdfinfo", path], capture_output=True, text=True, timeout=20).stdout
            m = _re.search(r"Pages:\s+(\d+)", out)
            if m:
                tot += int(m.group(1))
        except Exception:
            return None
    return tot or None

# ---------- SEARCH: 키워드 검색 인덱스 (A층 인덱스 요약 + B층 MD 본문) ----------
def build_search():
    import glob as g, re as _re
    rows = []

    def add(kind, rid, date, house, ctx, sub, text, page=None):
        text = (text or "").strip()
        if text:
            rows.append({"k": kind, "r": rid, "d": date or "", "h": house or "",
                         "c": ctx or "", "i": sub or "", "p": page or "", "x": text})

    # A층: 인덱스의 텍스트 필드 (회사·이슈·페이지 귀속)
    for s in stances:
        add("스탠스", s["report_id"], s["date"], s["house"], s["company"],
            ISSUE_ALIAS.get(s["issue"], s["issue"]), s["summary"], s.get("source_page"))
    for dr in drivers:
        add("드라이버", dr.get("source_file", ""), f'{dr["fy"]}.{dr["period"]}', "회사 IR",
            dr["company"], dr.get("segment_std", ""), dr["summary"], dr.get("source_page"))
    for iv in iviews:
        add("산업전망", iv["report_id"], iv["date"], iv["house"], iv.get("scope", ""),
            iv.get("metric", ""), iv["summary"], iv.get("source_page"))
    for th in csv.DictReader(open(f"{IDX}/themes.csv", encoding="utf-8")):
        txt = " / ".join(x for x in [th.get("summary"), th.get("bull"), th.get("bear")] if x)
        add("테마", th["report_id"], th["date"], th["house"], "산업", th["theme"],
            txt, th.get("source_page"))
    seen_basis = set()
    for dfr in csv.DictReader(open(f"{IDX}/demand_forecasts.csv", encoding="utf-8")):
        for fld in ("basis", "scope_note"):
            t = (dfr.get(fld) or "").strip()
            if not t or (dfr["report_id"], t) in seen_basis:
                continue
            seen_basis.add((dfr["report_id"], t))
            add("수요전망", dfr["report_id"], dfr["date"], dfr["house"],
                f'{dfr["region"]} {dfr["application"]}', dfr["metric"], t, dfr.get("source_page"))
    for r in reports:
        add("리포트 요약", r["report_id"], r["date"], r["house"], r["coverage"],
            r.get("report_type", ""), r.get("summary"))
    # B층: 표준 MD 본문 (frontmatter 제외, '## 섹션' 단위)
    for p in sorted(g.glob(os.path.join(ROOT, "reports", "*", "*.md"))):
        t = open(p, encoding="utf-8").read()
        parts = t.split("---", 2)
        if len(parts) < 3:
            continue
        rid = os.path.basename(p)[:-3]
        rm = rmeta.get(rid, {})
        for m in _re.finditer(r"^## (.+?)\n(.*?)(?=\n## |\Z)", parts[2], _re.S | _re.M):
            sec = m.group(1).strip()
            txt = _re.sub(r"<!--.*?-->", "", m.group(2), flags=_re.S).strip()
            if txt:
                add("본문", rid, rm.get("date", ""), rm.get("house", ""),
                    rm.get("coverage", ""), sec, txt)
    return rows


data = {"meta": {"built_from": "K-battery-financials index v2", "n_reports": len(reports),
                 "n_industry": sum(1 for r in reports if r.get("report_type") == "산업"),
                 "n_pages": total_pages(),
                 "n_estimates": len(est), "houses": sorted({r['house'] for r in reports}),
                 "period": f"{min(r['date'] for r in reports)} ~ {max(r['date'] for r in reports)}",
                 "note_basis": "영업이익 비교는 AMPC 포함(incl) 기준 통일. excl만 있는 경우 AMPC 가산 파생(derived). LGES 매출은 1Q26부터 AMPC 병합 표시(IR 재작성 기준)."},
        "f1_quarterly": f1, "f2_stance": f2, "f3_views": f3,
        "f3_narratives": f3_narr, "f4_accuracy": f4, "f5_outliers": f5, "f6_dotplots": f6, "f7_industry": f7,
        "search": build_search()}
json.dump(data, open(f"{OUT}/data.json", "w", encoding="utf-8"), ensure_ascii=False)
print(f"data.json 생성: {os.path.getsize(f'{OUT}/data.json')//1024}KB")
print(f"f2 {len(f2)}셀 / f3 {len(f3)}시리즈 / f4 이벤트 {len(f4['events'])}+빈티지 {len(f4['fy2025_vintage'])}행"
      f" / f5 추정치 {len(f5['estimate_outliers'])}·스탠스 {len(f5['stance_outliers'])} / f6 dots {sum(len(d['dots']) for d in f6['op_dots'])}")
