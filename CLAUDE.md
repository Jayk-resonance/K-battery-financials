# CLAUDE.md — K-battery-financials 작업 지침

이 저장소에서 작업할 때 세션 시작 시 **자동으로 읽히는 파일**이다.
맥락이 전혀 없는 상태로 첫 명령을 받아도, 이 문서만 따르면 올바른 절차를 밟도록 설계되었다.
Claude 외 도구(GPT·Gemini·Cursor 등)는 이 파일을 자동 로드하지 않으므로, 그런 도구를 위한
진입점은 `AGENTS.md`에 있다(같은 저장소 루트) — 이 문서로 그대로 이어진다.

## 0. 범용 코딩 지침 (모든 작업에 공통 적용)

**Tradeoff:** 아래는 속도보다 신중함에 무게를 둔다. 사소한 작업에는 판단력을 발휘한다.

1. **코딩 전에 생각한다** — 가정하지 않는다. 확신 없으면 묻는다. 여러 해석이 가능하면 제시하고 조용히 하나를 고르지 않는다.
2. **단순함 우선** — 요청한 것 이상을 만들지 않는다. 단발성 코드에 추상화를 두지 않는다. 200줄이 50줄로 될 수 있으면 다시 쓴다.
3. **외과적 변경** — 건드릴 것만 건드린다. 인접 코드를 "개선"하지 않는다. 기존 스타일을 따른다. 바뀐 줄은 전부 요청과 직결되어야 한다.
4. **목표 지향 실행** — "버그 수정" → "재현하는 테스트 작성 후 통과시키기"처럼 검증 가능한 목표로 바꾼다. 다단계 작업은 짧은 계획을 먼저 제시한다.

## 1. 이 저장소가 하는 일

2차전지 산업 + 3사(LG에너지솔루션·삼성SDI·SK온) 증권사 리포트를 **재사용 가능한 DB**로 관리하고,
자립형 HTML 대시보드를 생성·배포한다. 설계 철학은 `README.md` 참조.
핵심 한 줄: **원문(MD) 과 구조화 데이터(인덱스) 를 분리**한다.

## 2. 작업 전 반드시 읽을 문서 (순서대로)

1. `README.md` — 저장소 목적·폴더 구조·비개발자 사용법
2. `schema/template.md` — MD의 표준 양식(= DB 스키마). YAML 필드 정의 + 본문 6개 섹션 + 인제스트 입력 형식(부록)
3. `schema/NORMALIZATION.md` — 판단 규칙: segment_std 매핑, ampc_basis, metric 통제어휘, stance_score rubric(-10~+10), 이슈 통제어휘, 수요 시리즈 분류, KNOWN_OP_BASIS 자동 교정

인제스트/분석에 들어가기 전에 최소 위 3개를 읽는다. **규칙은 내 기억이 아니라 이 문서들에 있다.**

## 3. 데이터 흐름 (파이프라인)

```
inbox/*.pdf                                    # 원본 PDF (사용자가 넣음)
  │  ── [인제스트: PDF 읽고 프론트매터+본문 추출] ──
  ▼
.staging/<report_id>.json                      # 중간 산출물 (git 추적됨 — §6 참조)
  │  ── tools/build_indexes.py ──
  ▼
reports/YYYY/<report_id>.md                    # 표준 MD (영속 DB, 커밋됨)
index/{reports.jsonl,estimates.csv,stances.csv,industry_views.csv,actuals.csv,drivers.csv,demand_forecasts.csv,themes.csv}
  │  ── tools/build_dashboard_data.py ──
  ▼
projects/dashboard/data.json                   # 대시보드 데이터셋
  │  ── tools/assemble_dashboard.py ──
  ▼
projects/dashboard/dashboard.html              # 자립형 최종 결과물
  │  ── tools/deploy_pages.py ──
  ▼
docs/index.html                                # GitHub Pages 배포본
```

`report_id` = 파일명(확장자 제외) = `YYYY-MM-DD_증권사_커버리지` (커버리지: LGES|삼성SDI|SK온|산업).

## 4. 인제스트 절차

사용자가 "inbox의 리포트를 인제스트해줘"라고 하면:

1. **위 3개 문서를 읽는다** (template.md, NORMALIZATION.md 필수).
2. `inbox/`의 대상 PDF를 읽는다. `check_duplicates.py --new-only`로 중복(언어판 등)을 먼저 거른다.
3. 각 PDF를 `.staging/<report_id>.json`으로 추출한다. 키 구조는 `template.md` 부록 또는 기존 staging JSON 1~2개를 대조:
   `report_id,date,house,analyst,coverage,report_type,opinion,target_price,prev_target_price,key_issues,estimates,stances,industry_views,top_picks,body`.
   - 애매한 경계 케이스(스탠스 점수, 세그먼트 매핑, AMPC 표기)는 **유사한 기존 MD를 대조**해 일관성을 맞춘다.
   - 모든 숫자에 `page`를 남긴다 (감사 추적).
4. 각 신규 리포트를 `python3 tools/build_indexes.py --check-id <report_id>` 로 엄격 검증한다
   (파일 안 씀). 신규 ID의 경고가 1건이라도 있으면 종료코드 1로 실패하므로 먼저 수정한다.
   여러 건이면 `--check-id`를 반복 지정한다.
   이 절차를 빠뜨려도 실제 재빌드 전에 신규 ID 경고를 다시 검사해 자동 중단한다.
5. `python3 tools/build_indexes.py --check` 로 전체 DB 회귀 검증을 확인한다.
   기존 레거시 경고와 신규 리포트 합격 판정은 분리하며, 신규 ID는 반드시 대상 경고 0건이어야 한다.
6. 통과하면 `python3 tools/build_indexes.py` 로 MD 렌더 + 인덱스 재빌드.
7. 대시보드까지 갱신이 필요하면: `python3 tools/build_dashboard_data.py && python3 tools/assemble_dashboard.py`.

절차가 이 6단계로 짧으므로 별도 INGEST.md는 두지 않는다. 규칙이 두꺼워지면 그때 분리.

**이슈 태깅 주의(자주 헷갈리는 것)**: `AMPC`(미국 정부 IRA 생산세액공제)와 `OEM보상금`(완성차 고객사 수취 보상금 — 최소구매 미달·물량 미납·설비·JV 청산 등 일회성)은 **다른 이슈**다. 한 리포트가 둘 다 다루면 **각각 스탠스 행을 따로** 붙인다(1문장이 여러 이슈면 여러 행). 전체 이슈 통제어휘·구분 기준은 `schema/NORMALIZATION.md §6`.

## 5. 대시보드 재생성 + 웹 배포

UI/차트 로직 = `projects/dashboard/dashboard_template.html`(코드), 데이터 = `data.json`, 서술 = `narratives.json`.
템플릿의 `/*__DATA__*/` 자리에 data.json이 주입되어 자립형 `dashboard.html`이 나온다.

```bash
python3 tools/build_dashboard_data.py   # index/ + narratives.json → data.json
python3 tools/assemble_dashboard.py     # template + data.json → dashboard.html
python3 tools/deploy_pages.py           # dashboard.html → docs/index.html (Pages 배포본)
git add docs && git commit -m "deploy: 대시보드 갱신" && git push
```

같은 인덱스에서 실행하면 결정적으로 같은 결과가 나온다(재해석 개입 없음).

- **`docs/index.html`은 생성물이다. 직접 편집하지 않는다** — 다음 배포 때 덮어쓰인다.
  화면을 고치려면 `dashboard_template.html`(UI) 또는 데이터 파이프라인을 고치고 위 단계를 다시 돈다.
- GitHub Pages의 소스 설정(저장소 Settings → Pages → Branch)이 이 브랜치의 `/docs`를 가리켜야 실제로 게시된다. 최초 1회는 사람이 GitHub UI에서 켜야 한다(git으로 자동화 불가).

## 6. 운영 규칙

- **원천 불가침**: `reports/`·`index/`는 분석 과정에서 절대 손으로 수정하지 않는다. 분석 결과는 `projects/<이름>/`에만 쓴다. 인덱스는 스크립트로만 재생성한다.
- **표기 오류 교정은 스테이징이 아니라 코드에서**: 실적 확정 기간의 OP basis 교정은 `build_dashboard_data.py`의 `KNOWN_OP_BASIS`, metric 동의어는 `build_indexes.py`의 `METRIC_STD`, 수요 시리즈 분류는 `demand_curation.py`에서만 수정한다. 원본 인덱스는 건드리지 않는다.
- **.staging/**: JSON 전부를 **git으로 추적한다**. staging이 MD·인덱스를 재생성하는 유일한 소스이므로, 없으면 `build_indexes.py`가 DB를 비운다(그래서 축소 재빌드는 자동 차단되고 `--force`로만 강행 가능). 여러 사람·여러 LLM이 나눠 인제스트할 때도 staging 공유가 필수다.
- **inbox/·actuals/의 원본 PDF는 증권사 저작물이다.** 이 저장소는 공개(public)이므로 재배포 범위에 유의한다.
- **Artifact 재게시**: 대시보드를 Claude Artifact로 올릴 때는 **반드시 기존 URL을 `url` 파라미터로 지정**한다(안 하면 새 URL이 발급됨).

## 7. 새 실적 발표 시 갱신 체크리스트

분기 실적이 발표되면 **코드에 하드코딩된 지점 5곳 + 큐레이션 서술 4곳**을 손봐야 한다.
안 하면 조용히 낡은 값이 표시된다(오류가 나지 않으므로 더 위험).

**A. 코드 (실적 확정 시 필수)** — `tools/build_dashboard_data.py`

| 대상 | 무엇을 | 안 하면 |
|---|---|---|
| `ANNOUNCE` | (회사, 연도, 분기): 발표일 추가 | 아웃라이어 분석 대상 분기가 안 넘어감 |
| `KNOWN_OP_BASIS` | 실적 확정 OP의 incl/excl 값 추가 | 점도표 basis 자동교정 누락 → 이탈점 발생 |
| `KNOWN_ANNOUNCE` | 발표일 추가 | 발표 후 기준 불일치 점이 안 걸러짐 |
| `skon_quarters()` | SK온 새 분기 cutoff 추가 | SK온 실적선이 안 그려짐 |
| `QFY` | 분석연도 (3Q 실적 후 다음 해로) | 분기 점도표·아웃라이어가 옛 연도 고정 |

`F5_TARGETS`(아웃라이어 대상 분기·연도)는 `ANNOUNCE` 기준으로 **자동 롤링**되므로 손대지 않는다.

**B. 큐레이션 서술 (숫자가 바뀌면 갱신)**

| 대상 | 위치 | 성격 |
|---|---|---|
| `F1HEAD` / `F4WHY` / `F6GAP` | `dashboard_template.html` | 차트 헤드메시지 — **차트 숫자와 대조 필수** |
| `narratives.json` | `projects/dashboard/` | QoQ 손익 차이분석(분기별 브리핑) |
| `issue_summaries.json` | `projects/dashboard/` | 이슈별 긍정/부정 요약 |

- `issue_summaries.json`은 **staleness 자동 감지**가 있다: 하우스 구성이 바뀌면 빌드 시
  `[STALE] 요약 재생성 필요: <이슈>|<회사>` 경고가 뜬다 → 그 셀만 재생성한다.
- 헤드메시지는 감지 장치가 없다. **데이터가 바뀐 뒤에는 반드시 차트 값과 눈으로 대조**한다
  (과거에 십억원↔억원 10배 오차, 매출 정규화 후 8.2조→8.46조 불일치 사례가 있었다).

**C. 순서**: 인제스트(§4) → A 갱신 → `build_dashboard_data.py`(STALE 경고 확인)
→ B 갱신 → 재빌드 → `assemble_dashboard.py` → `deploy_pages.py` → 스크린샷으로 헤드메시지·차트 대조.

## 8. 현재 상태를 확인하는 법 (숫자를 여기 박지 말 것)

상태값은 시간이 지나면 썩으므로 이 문서에 카운트를 하드코딩하지 않는다. 필요하면 그때 확인한다:

- 리포트 수: `wc -l index/reports.jsonl`
- 커버리지·기간 분포: `index/reports.jsonl` 조회
- 대시보드 버전 이력·최신 커밋: `git log --oneline` (진실의 원천은 git)
- 스키마 버전: `schema/NORMALIZATION.md` 제목줄
