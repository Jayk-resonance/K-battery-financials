#!/usr/bin/env python3
"""rescore_<house>.json 패치를 스테이징 리포트 JSON에 적용 (-10~+10 전환)."""
import json, glob, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ST = os.path.join(ROOT, ".staging")
applied = skipped = 0
dist = collections.Counter()
warn = []
for pf in sorted(glob.glob(f"{ST}/rescore_*.json")):
    d = json.load(open(pf, encoding="utf-8"))
    for patch in d.get("patches", []):
        rp = f"{ST}/{patch['report_id']}.json"
        if not os.path.exists(rp):
            warn.append(f"리포트 없음: {patch['report_id']}")
            continue
        r = json.load(open(rp, encoding="utf-8"))
        cur = r.get("stances", [])
        pat = patch.get("stances", [])
        if len(cur) != len(pat):
            warn.append(f"{patch['report_id']}: 항목 수 불일치 ({len(cur)} vs {len(pat)}) — (issue,company) 매칭으로 폴백")
            index = {}
            for p in pat:
                index.setdefault((p["issue"], p["company"]), []).append(p)
            for s in cur:
                lst = index.get((s["issue"], s["company"]))
                if lst:
                    p = lst.pop(0)
                    s["stance_score"] = max(-10, min(10, int(p["new_score"])))
                    dist[s["stance_score"]] += 1
                    applied += 1
                else:
                    skipped += 1
        else:
            for s, p in zip(cur, pat):
                if s["issue"] != p["issue"] or s["company"] != p["company"]:
                    warn.append(f"{patch['report_id']}: 순서 불일치 {s['issue']}/{s['company']} vs {p['issue']}/{p['company']}")
                    skipped += 1
                    continue
                s["stance_score"] = max(-10, min(10, int(p["new_score"])))
                dist[s["stance_score"]] += 1
                applied += 1
        json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
print(f"적용 {applied}건 / 스킵 {skipped}건 / 경고 {len(warn)}건")
for w in warn[:10]:
    print(" ", w)
print("점수 분포:", dict(sorted(dist.items())))
