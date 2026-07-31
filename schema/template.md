---
# ─────────────────────────────────────────────────────────────
# 리포트 표준 메타데이터 (= DB의 '컬럼'). 매 인제스트마다 이 형식을 강제한다.
# 값을 모르면 빈칸이 아니라 null 로 둔다. 숫자는 단위를 unit 에 명시한다.
# ─────────────────────────────────────────────────────────────
report_id: 2026-01-15_미래에셋_LGES     # = 파일명(확장자 제외). YYYY-MM-DD_증권사_커버리지
date: 2026-01-15                        # 리포트 발간일 (YYYY-MM-DD)
house: 미래에셋                          # 증권사
analyst: null                           # 애널리스트명 (없으면 null)
coverage: LGES                          # LGES | 삼성SDI | SK온 | 산업
report_type: 기업                        # 기업 | 산업
opinion: 매수                            # 매수 | 중립 | 매도 | null (산업리포트면 null)
target_price: 450000                    # 목표주가(원). 없으면 null
prev_target_price: 420000               # 직전 목표주가(원). 상향/하향 델타 계산용. 없으면 null

# 세그먼트/전사 손익·추정치. estimates.csv 로도 펼쳐진다. (스키마 v2)
# segment: 원문 그대로 / segment_std: NORMALIZATION.md 매핑 / period: FY|1Q~4Q
# ampc_basis: excl|incl|incl_unknown|na / AMPC 금액은 metric=AMPC 별도 행
estimates:
  - {company: LGES, segment: 전사, segment_std: 전사, fy: 2026, period: FY, metric: 영업이익, value: 993, unit: 십억원, ampc_basis: incl, page: 3}
  - {company: LGES, segment: 전사, segment_std: 전사, fy: 2026, period: FY, metric: AMPC, value: 1425, unit: 십억원, ampc_basis: na, page: 3}
  - {company: LGES, segment: ESS, segment_std: ESS, fy: 2026, period: 2Q, metric: 매출, value: 2062, unit: 십억원, ampc_basis: excl, page: 3}

# 이슈별 스탠스. stances.csv 로도 펼쳐진다.
# stance_score: -10 ~ +10 (NORMALIZATION.md 6절 rubric 참조)
stances:
  - {issue: LFP,      company: LGES, stance_score: 5,  summary: "26년 하반기 양산 목표, 경쟁사 대비 1년 후행", page: 5}
  - {issue: 북미CAPEX, company: LGES, stance_score: -4, summary: "IRA 불확실성으로 증설 속도 조절 가능성", page: 6}

key_issues: [LFP, 북미CAPEX, 수율]        # 이 리포트가 다룬 이슈 태그
# 산업 리포트/산업 전망 포함 시 (없으면 빈 리스트)
industry_views:
  - {scope: 북미ESS, fy: 2026, metric: 수요, value: null, unit: GWh, direction: 2, summary: "AI 데이터센터發 수요 급증", page: 2}
top_picks: []                             # 산업 리포트의 최선호주
source_pdf: inbox/미래에셋_20260115.pdf   # 원본 경로 (모든 숫자의 감사 추적용)
---

## 핵심 요약
<!-- 3~5줄. 이 리포트의 결론. -->

## 투자의견·목표주가 (도출 근거)
<!-- 밸류에이션 방식(EV/EBITDA, P/B 등), 멀티플, 목표주가 산출 논리. 직전 대비 변경 사유. -->

## 사업부문별 손익
<!-- 회사·세그먼트별 매출/영업이익/영업이익률/출하량 표. frontmatter estimates 와 일치시킬 것. -->

## 이슈별 코멘트
<!-- LFP / 46파이 / ESS / 북미CAPEX / 수율 등. frontmatter stances 와 일치시킬 것. -->

## 리스크 요인
<!-- 하방 리스크. 태그화 가능하도록 항목별로. -->

## 원문 인용
<!-- 핵심 주장은 원문 그대로 보존. 환각 방지 + 감사 가능. (p.N) 형식으로 페이지 표기. -->

---

# 부록. 인제스트 입력 형식 — `.staging/<report_id>.json`

**위 MD는 직접 쓰지 않는다.** 인제스트는 staging JSON을 만들고, `tools/build_indexes.py`가
그 JSON에서 위 MD와 `index/*`를 **자동 생성**한다. 따라서 아래 키 이름을 정확히 맞춰야 한다.

```jsonc
{
  "report_id": "2026-01-15_미래에셋_LGES",   // = 파일명(확장자 제외)
  "date": "2026-01-15", "house": "미래에셋", "analyst": null,
  "coverage": "LGES",            // LGES | 삼성SDI | SK온 | 산업
  "report_type": "기업",          // 기업 | 산업
  "opinion": "매수",              // 매수 | 중립 | 매도 | null(산업)
  "target_price": 450000, "prev_target_price": 420000,
  "key_issues": ["LFP", "북미CAPEX"],
  "top_picks": [],                            // 산업 리포트만
  "estimates": [ { /* company, segment, segment_std, fy, period, metric, value, unit, ampc_basis, page */ } ],
  "stances":   [ { /* issue, company, stance_score, summary, page */ } ],
  "industry_views": [ { /* scope, fy, metric, value, unit, direction, summary, page */ } ],
  "demand_forecasts": [ /* 산업 v3 — NORMALIZATION.md §8 */ ],
  "themes":          [ /* 산업 v3 — NORMALIZATION.md §8 */ ],
  "body": { "summary": "...", "valuation": "...", "segment_pl": "...",
            "issue_comments": "...", "risks": "...", "quotes": "..." }
}
```

**`body` 6개 키 → MD 섹션 매핑** (키 이름이 틀리면 그 섹션이 **오류 없이 빈 채로** 생성된다)

| body 키 | MD 섹션 |
|---|---|
| `summary` | `## 핵심 요약` |
| `valuation` | `## 투자의견·목표주가 (도출 근거)` |
| `segment_pl` | `## 사업부문별 손익` |
| `issue_comments` | `## 이슈별 코멘트` |
| `risks` | `## 리스크 요인` |
| `quotes` | `## 원문 인용` |

- 각 값은 문자열 또는 문자열 리스트(리스트는 개행으로 결합된다). `null`은 빈 섹션이 된다.
- `estimates`·`stances`의 값 규칙(단위 십억원, segment_std, ampc_basis, metric 통제어휘,
  stance_score −10~+10)은 `NORMALIZATION.md` 를 따른다.
- 작성 후 반드시 `python3 tools/build_indexes.py --check` 로 경고를 확인한다.
  `metric 비표준`·`segment_std 강제`·`stance_score 범위 밖` 경고는 **데이터가 새는 신호**다.
