# K-battery-financials — K-배터리 증권사 리포트 DB + 대시보드

2차전지 산업 및 3사(LG에너지솔루션·삼성SDI·SK온) 증권사 리포트를 **재사용 가능한 DB**로 관리하고,
자립형 HTML 대시보드로 시각화·배포하는 저장소.

## 핵심 원리

> **원문(MD)** 과 **구조화 데이터(인덱스)** 를 분리한다.

- `reports/` 의 MD = 사람과 AI가 **읽는** 전체 원문 (맥락)
- `index/` 의 CSV·JSONL = **필터·집계·차트**용 정형 데이터 (점도표, 컨센서스, 비교표의 연료)

각 리포트 MD는 상단 **YAML frontmatter(구조화 메타데이터)** + 하단 **표준 본문**으로 구성된다.
frontmatter 필드가 곧 "DB 컬럼"이다. 표준 양식은 [`schema/template.md`](schema/template.md).

## 폴더 구조

```
├── inbox/                    # ← 원본 PDF를 여기 넣는다 (사용자의 유일한 수작업)
├── .staging/                 # 인제스트 중간 산출물(JSON). git 추적됨 — 재빌드의 유일한 소스
├── reports/YYYY/              # 표준 MD. 파일명 = YYYY-MM-DD_증권사_커버리지.md
├── earnings/YYYY/             # 회사 실적·컨퍼런스콜 표준 MD
├── index/
│   ├── reports.jsonl          # 리포트 1건 = 1행
│   ├── estimates.csv          # (리포트×회사×세그먼트×지표×기간) 추정치
│   ├── stances.csv            # (리포트×이슈×회사) 이슈별 스탠스
│   └── ...                    # industry_views·themes·actuals·drivers·guidance·call_qa
├── schema/
│   ├── template.md            # 표준 MD 양식 + 인제스트 입력 형식(부록)
│   ├── earnings_template.md   # 실적·컨콜 전용 입력·MD 형식
│   └── NORMALIZATION.md       # 판단 규칙(segment_std·ampc_basis·metric·이슈 통제어휘)
├── tools/                     # 인제스트·빌드·배포 스크립트
├── projects/dashboard/        # 대시보드 데이터·템플릿·자립형 산출물
├── docs/                      # GitHub Pages 배포본 (생성물, 직접 편집 금지)
├── actuals/                   # 회사 IR 원본(정답지)
└── personas/                  # 증권사 페르소나(멀티에이전트 분석용)
```

## 사용법 (비개발자)

### 1) 리포트 넣기 (인제스트)
1. PDF를 `inbox/` 에 넣는다.
2. Claude에게: **"inbox의 리포트를 인제스트해줘"**
   → PDF를 `schema/template.md` 형식의 MD로 변환해 `.staging/`에 저장 후 `reports/YYYY/` 에 렌더
   → `index/` 를 `.staging/` 전체로부터 재생성한다(전량 재빌드 — 결정적·재현 가능).
   → 원본 PDF 경로와 페이지를 남겨 **모든 숫자를 역추적** 가능하게 한다.

### 1-1) 실적·컨퍼런스콜 넣기
1. 회사 IR·컨콜 원본을 `actuals/`에 넣는다.
2. Claude에게: **"actuals의 이번 분기 실적·컨콜을 인제스트해줘"**
   → `schema/earnings_template.md`에 따라 회사×분기 1개 JSON을 만든다.
   → `earnings/YYYY/` 표준 MD와 actuals·drivers·guidance·Q&A 인덱스를 함께 재생성한다.
   → 원문이 없는 가이던스·Q&A는 추정해 채우지 않고 미수록 사유를 남긴다.

### 2) 분석하기
Claude에게 원하는 분석을 요청하면 `index/` 를 조회해 `projects/<이름>/` 에 결과를 쓴다. 예:
- "삼성SDI 목표주가를 증권사별 시계열로 보여줘" (→ estimates.csv)
- "LFP·46파이·ESS·AMPC·수율에 대한 3사 비교표를 만들어줘" (→ stances.csv)
- "2026E 3사 영업이익 추정치로 FOMC식 점도표를 그려줘" (→ estimates.csv)
- "미래에셋의 SK온 View가 시간에 따라 어떻게 바뀌었는지 추적해줘"

### 3) 대시보드 보기 / 배포하기
`projects/dashboard/dashboard.html` 이 자립형 최종 산출물이다(브라우저로 바로 열림).
GitHub Pages로 배포하려면 `tools/deploy_pages.py` → `docs/index.html` → 커밋·푸시.
자세한 절차는 [`CLAUDE.md`](CLAUDE.md) 참조.

## 시작 규모 권장
100개를 한 번에 하지 말 것. **한 분기(약 20개)로 스키마를 먼저 검증** → 분석 2~3개를 실제로 돌려
스키마가 그 분석을 지탱하는지 확인 → 전량 확장. (과잉설계 방지)

## 성장 경로
연 200~300건 수준이면 이 방식(MD + CSV/JSONL)으로 수 년간 충분하다.
정말 커지거나 실시간 다중 조회가 필요해지면 그때 `index/` 만 SQLite(파일 1개)로 승격하면 된다.
지금은 불필요하다.
