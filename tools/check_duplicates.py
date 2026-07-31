#!/usr/bin/env python3
"""신규 인제스트 전 중복 후보 탐지 (NORMALIZATION.md 7절).

규칙: 같은 (하우스, 커버리지) + 발간일 차이 2일 이내 → 중복 후보로 플래그.
후보는 제목·첫 페이지 텍스트를 사람이(또는 에이전트가) 대조해 판정하고,
중복 확정 시 한국어판 1건만 남기고 나머지는 archive/duplicates/로 이동(git mv),
manifest 항목에 duplicate_of: <남긴 report_id> 를 기록한다. 삭제하지 않는다.

사용법: python3 tools/check_duplicates.py           # 전체 스캔
        python3 tools/check_duplicates.py --new-only # manifest에 없는 inbox 신규 파일만 대조
"""
import json, os, sys, re, collections
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mf = json.load(open(f"{ROOT}/.staging/manifest.json", encoding="utf-8"))
mf = [m for m in mf if not m.get("duplicate_of")]

COMPANY = {"LG에너지솔루션": "LGES", "삼성SDI": "삼성SDI", "SK이노베이션": "SK온"}


def keyof(f):
    parts = f[:-4].split("_")
    house = parts[0]
    cov = COMPANY.get(parts[1] if len(parts) > 2 else "", "산업")
    m = re.search(r"(\d{8})$", f[:-4])
    d = date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:])) if m else None
    return house, cov, d


new_only = "--new-only" in sys.argv
known = {m["file"] for m in mf}
inbox = [f for f in sorted(os.listdir(f"{ROOT}/inbox")) if f.endswith(".pdf")]
targets = [f for f in inbox if f not in known] if new_only else inbox

pool = collections.defaultdict(list)
for f in inbox:
    h, c, d = keyof(f)
    if d:
        pool[(h, c)].append((d, f))

flags = []
for f in targets:
    h, c, d = keyof(f)
    if not d:
        continue
    for d2, f2 in pool[(h, c)]:
        if f2 != f and abs((d2 - d).days) <= 2:
            pair = tuple(sorted([f, f2]))
            if pair not in [p["pair"] for p in flags]:
                flags.append({"pair": pair, "house": h, "coverage": c,
                              "gap_days": abs((d2 - d).days)})

if not flags:
    print("중복 후보 없음 ✓")
else:
    print(f"⚠ 중복 후보 {len(flags)}쌍 — 제목·본문 대조 후 판정 필요:")
    for p in flags:
        print(f"  [{p['house']}·{p['coverage']}·{p['gap_days']}일차]")
        print(f"    {p['pair'][0]}")
        print(f"    {p['pair'][1]}")
    print("\n중복 확정 시: 한국어판 1건 유지, 나머지 git mv inbox/<파일> archive/duplicates/")
    print("+ manifest 해당 항목에 \"duplicate_of\": \"<유지한 report_id>\" 추가 (build_indexes가 자동 제외)")
sys.exit(1 if flags else 0)
