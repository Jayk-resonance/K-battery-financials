# 시장·회사 정량 데이터 표준 스키마 (v1 설계 기준)

EV·ESS 시장 데이터와 배터리 회사의 판매량·생산능력 데이터를 보고서·Excel에서
재사용하기 위한 표준이다. 이 문서는 스키마와 정규화의 기준이며, 실제 검증 코드·인덱스·백필은
후속 단계에서 구현한다.

## 1. 설계 원칙

1. **시장과 회사는 분리한다.** 시장 데이터는 `market_series`, 회사 데이터는
   `company_volume_series`에 저장하고 서로 다른 인덱스로 생성한다.
2. **원문을 보존한다.** 표준값과 함께 원문 지역·지표·단위·측정기준을 남긴다.
3. **숫자를 만들지 않는다.** 환산 근거가 없는 차량 대수·셀 개수는 GWh로 임의 환산하지 않는다.
4. **모든 숫자는 역추적 가능해야 한다.** 리포트 ID·페이지·표/차트·최초 출처를 남긴다.
5. **부모 지역과 하위 지역을 더하지 않는다.** 북미 전체값과 미국값은 별도 시리즈다.
6. **실적과 전망을 섞지 않는다.** 실제·추정·가이던스·시나리오를 구분한다.
7. **현재 인덱스는 하위호환으로 유지한다.** `demand_forecasts.csv`는 새 시장 인덱스에서
   파생할 수 있을 때까지 유지한다.

## 2. 공통 출처·시리즈 필드

`report_id`, `date`, `house`는 리포트 상단에서 상속한다. 각 정량 행은 아래 필드를 가진다.

| 필드 | 필수 | 허용값·형식 | 의미 |
|---|---:|---|---|
| `series_id` | 예 | 리포트 내 시계열 고유 문자열 | 같은 표·범위·지표의 기간별 값을 연결하는 키 |
| `fy` | 예 | 정수 | 대상 연도 |
| `period` | 예 | `FY`, `1Q`~`4Q`, `01M`~`12M`, `YTD` | 대상 기간 |
| `value_type` | 예 | `실적`, `추정`, `가이던스`, `시나리오` | 숫자의 성격 |
| `basis` | 예 | 원문 기준 설명 | 포함·제외 범위와 산정 기준 |
| `scope_note` | 아니오 | 문자열 또는 `null` | 중국 제외, 특정 고객 한정 등 비교 범위 |
| `source_owner` | 아니오 | 기관·회사명 또는 `null` | SNE Research, BNEF, IEA, 회사 IR 등 최초 출처 |
| `source_kind` | 예 | `회사공시`, `조사기관`, `증권사추정`, `증권사재가공`, `원천불명` | 최초 값의 성격 |
| `extraction_method` | 예 | `표`, `차트`, `본문`, `계산`, `원천불명` | 숫자를 얻은 방법. 기존 자료에서 확인할 수 없으면 `원천불명` |
| `value_precision` | 예 | `정확`, `근사`, `파생` | 표 직접 추출·차트 판독·계산값 구분 |
| `page` | 예 | 1 이상의 정수 | PDF 페이지 |

### `series_id` 규칙

- 같은 시계열의 여러 기간 행에는 같은 ID를 반복한다.
- 같은 ID 안의 시장·회사·지역·지표·단위 등 차원 필드는 일관되어야 한다.
- `(series_id, fy, period)` 조합은 리포트 안에서 한 번만 허용한다.
- 기간(`fy`, `period`)은 넣지 않는다. 한 시리즈의 여러 연도를 연결하기 위해서다.
- 예: `p55_us_ess_datacenter_demand`, `p18_catl_ev_sales`.
- 같은 지역·지표라도 중국 포함/제외, 실제/시나리오, 전체/부분시장은 서로 다른 ID를 쓴다.
- 월간 수치를 `FY`로 저장하지 않는다. 월이 명확하면 `01M`~`12M`, 누적이면 `YTD`를 쓰고
  누적 기준월이 불명확하면 자동 이관하지 않는다.

## 3. 지역 표준

시장과 회사 데이터는 같은 지역 필드를 사용한다.

| 필드 | 예 | 설명 |
|---|---|---|
| `geography_raw` | `US`, `미국`, `North America` | 원문 표현 |
| `geography` | `미국`, `북미` | 표준 조회명 |
| `parent_geography` | `북미`, `글로벌` | 상위 지역 |
| `geography_level` | `글로벌`, `권역`, `국가` | 집계 단계 |

규칙:

- 미국: `geography=미국`, `parent_geography=북미`, `geography_level=국가`.
- 북미 전체: `geography=북미`, `parent_geography=글로벌`, `geography_level=권역`.
- 미국을 북미로 치환하지 않는다.
- 북미 전체값이 있으면 미국·캐나다 값을 더해 덮어쓰지 않는다.
- 하위 국가 합산으로 북미를 계산할 경우 `extraction_method=계산`, `value_precision=파생`으로
  별도 시리즈를 만든다.
- 원문이 지역을 구분하지 않으면 추정하지 않고 `geography=글로벌` 또는 원문 범위에 맞는
  가장 굵은 단계로 둔다.

## 4. 시장 데이터 — `market_series`

### 4-1. 필드

| 필드 | 필수 | 허용값·형식 | 의미 |
|---|---:|---|---|
| `market` | 예 | `EV`, `ESS` | 시장 구분 |
| `application` | 예 | 아래 통제어휘 | ESS 용도. EV는 v1에서 `전체`가 기본 |
| `system_type` | 아니오 | `UPS`, `BESS`, `null` | ESS 시스템 형태. 원문 미구분은 `null` |
| `geography_raw` | 예 | 문자열 | 원문 지역 |
| `geography` | 예 | 표준 지역명 | 조회 지역 |
| `parent_geography` | 아니오 | 표준 지역명 또는 `null` | 상위 지역 |
| `geography_level` | 예 | `글로벌`, `권역`, `국가` | 지역 단계 |
| `metric` | 예 | 아래 통제어휘 | 시장 지표 |
| `value` | 예 | 숫자 | 원문 또는 표준값 |
| `value_prev` | 아니오 | 숫자 또는 `null` | 같은 리포트가 명시한 직전 전망치 |
| `unit` | 예 | 지표별 허용 단위 | 값의 단위 |
| `series_class` | 예 | `시장전체`, `서브세그먼트`, `시나리오`, `월간·누적`, `참고치` | 비교 가능성 분류 |
| `subsegment_raw` | 아니오 | 문자열 또는 `null` | BEV·PHEV·특정 기술 등 v1 비표준 세부범위 |
| 공통 필드 | 예 | §2·§3 | 기간·출처·페이지·시리즈 정보 |

### 4-2. ESS Application 통제어휘

- `전체`
- `Grid/Utility`
- `데이터센터`
- `상업·산업용(C&I)`
- `주거용`
- `통신 등 기타`

원문 세부 표현은 `subsegment_raw`에 보존한다. `system_type`은 `UPS`, `BESS`, `null`만
허용하며, 원문 근거 없이 시스템 형태를 추정하지 않는다.

### 4-3. 시장 지표·단위

| `metric` | 허용 단위 | 비고 |
|---|---|---|
| `수요량` | `GWh` | 배터리 에너지 수요 |
| `설치에너지` | `GWh` | ESS 설치 에너지 용량 |
| `설치출력` | `GW` | ESS 설치 출력. GWh와 합산 금지 |
| `판매대수` | `대`, `천대`, `만대`, `백만대` | EV 시장 차량 대수 |
| `성장률` | `%` | 전년 대비 등 기준을 `basis`에 명시 |
| `침투율` | `%` | 분모를 `basis`에 명시 |
| `점유율` | `%` | 대상 회사·기술·지역을 `basis`에 명시 |

`실적치`는 지표가 아니다. 기존 데이터의 `metric=실적치`는 실제 무엇의 실적인지 PDF 또는
원문 맥락을 확인해 위 지표로 재분류하고 `value_type=실적`으로 옮긴다.

### 4-4. 시장 데이터 예시

```jsonc
{
  "series_id": "p55_us_ess_datacenter_demand",
  "market": "ESS",
  "application": "데이터센터",
  "system_type": "UPS",
  "geography_raw": "US",
  "geography": "미국",
  "parent_geography": "북미",
  "geography_level": "국가",
  "metric": "수요량",
  "fy": 2030,
  "period": "FY",
  "value": 35.0,
  "value_prev": null,
  "unit": "GWh",
  "value_type": "추정",
  "series_class": "서브세그먼트",
  "subsegment_raw": "데이터센터 UPS용",
  "basis": "미국 데이터센터 UPS 배터리 수요",
  "scope_note": null,
  "source_owner": "BNEF",
  "source_kind": "조사기관",
  "extraction_method": "표",
  "value_precision": "정확",
  "page": 55
}
```

## 5. 회사 데이터 — `company_volume_series`

### 5-1. 회사 범위

- LG에너지솔루션, 삼성SDI, SK온을 포함한 모든 배터리 셀 기업을 대상으로 한다.
- CATL, BYD, Panasonic, CALB, EVE Energy, Gotion, Sunwoda, Farasis,
  Envision AESC 등 신규 회사가 발견되면 회사 사전에 추가한다.
- 원문명과 표준명을 함께 보존한다.
- OEM·배터리 통합기업과 JV 법인은 `company_type`으로 구분하고 다른 회사에 합치지 않는다.
- 모회사의 생산능력이 JV 공장에 있는지는 `company_type`이 아니라 `ownership_type`으로 구분한다.

### 5-2. 필드

| 필드 | 필수 | 허용값·형식 | 의미 |
|---|---:|---|---|
| `company_raw` | 예 | 원문 회사명 | 원문 보존 |
| `company` | 예 | 표준 회사명 | 별칭 통합용 |
| `company_type` | 예 | `배터리셀`, `통합OEM·배터리`, `JV`, `기타` | 회사 유형 |
| `facility_raw` | 아니오 | 원문 공장·사이트명 또는 `null` | 울산, Ultium Cells Tennessee 등 원문 설비명 |
| `ownership_type` | 생산능력만 예 | `단독`, `JV`, `혼합`, `불명` | 해당 생산능력의 소유·운영 형태 |
| `jv_name_raw` | 아니오 | 원문 JV명 또는 `null` | 원문에 명시된 합작법인·프로젝트명 |
| `jv_partner_raw` | 아니오 | 원문 파트너명 또는 `null` | 원문에 명시된 JV 파트너. 추정 금지 |
| `capacity_basis` | 생산능력만 예 | `총설비`, `지분귀속`, `불명` | 공장 전체 GWh인지 회사 지분 귀속 GWh인지 구분 |
| `market` | 예 | `EV`, `ESS`, `합계` | 제품 용도. 미분리 값은 `합계` |
| `application` | 예 | §4-2 또는 `전체` | ESS 용도. EV·합계는 기본 `전체` |
| `system_type` | 아니오 | `UPS`, `BESS`, `null` | ESS만 사용 |
| `geography_raw` | 예 | 문자열 | 원문 지역 |
| `geography` | 예 | 표준 지역명 | 조회 지역 |
| `parent_geography` | 아니오 | 표준 지역명 또는 `null` | 상위 지역 |
| `geography_level` | 예 | `글로벌`, `권역`, `국가` | 지역 단계 |
| `metric` | 예 | `판매량`, `생산능력` | 사용자 조회 지표 |
| `metric_raw` | 예 | `출하량`, `생산량`, `설치량`, `판매량`, `생산능력` | 원문 측정기준 |
| `value` | 예 | 숫자 | GWh로 표준화한 값 |
| `unit` | 예 | `GWh` | 회사 데이터 표준 단위 |
| `raw_value` | 예 | 숫자 | 원문 값 |
| `raw_unit` | 예 | `MWh`, `GWh`, `TWh` | 원문 단위 |
| `time_basis` | 예 | `기간판매량`, `연환산생산능력`, `기준일생산능력` | 유량과 생산능력 구분 |
| `as_of_date` | 아니오 | `YYYY-MM-DD` 또는 `null` | 기준일 생산능력의 기준일 |
| 공통 필드 | 예 | §2·§3 | 기간·출처·페이지·시리즈 정보 |

### 5-3. 판매량 통합 규칙

- 원문 `출하량`, `생산량`, `설치량`, `판매량`은 사용자 조회에서 모두
  `metric=판매량`으로 통일한다.
- 원문 차이는 `metric_raw`에 반드시 보존한다.
- `metric_raw`가 다른 값은 자동 합산하지 않는다. 생산량과 판매량은 재고 변동 때문에 다를 수 있다.
- 동일 회사·기간에 여러 측정기준이 있으면 모두 보존하고 Excel에서 원문 측정기준으로 필터한다.
- `생산능력`은 판매량과 절대 합산하지 않는다.

### 5-4. 단위와 제외 규칙

- 회사 데이터의 표준 단위는 `GWh`다.
- MWh는 `÷1,000`, TWh는 `×1,000`으로 GWh 환산한다.
- 차량 대수·셀 개수·공장 라인 수는 명시적 에너지 환산 근거가 없으면 회사 표준 인덱스에서
  제외하고 검토 대상으로 남긴다.
- 억원·달러·시장금액·매출액 등 금액 데이터는 `company_volume_series`에 넣지 않는다.
- 생산능력은 표준값을 GWh로 저장하되 `time_basis`로 연환산 또는 기준일 능력을 구분한다.
- 생산능력은 `market`으로 EV·ESS·미분리 합계를 구분하고, 지역 필드와 `facility_raw`로
  권역·국가·공장 범위를 보존한다.
- JV 여부가 원문에 없으면 추정하지 않고 `ownership_type=불명`으로 둔다.
- JV 생산능력은 원문에 제시된 공장 전체 값을 `capacity_basis=총설비`로 저장한다.
  지분율을 적용한 값은 원문에 명시되었을 때만 별도 시리즈로 `capacity_basis=지분귀속` 처리한다.
- 글로벌·권역 합계에 단독 설비와 JV 설비가 함께 포함됐다고 명시되면 `ownership_type=혼합`으로 둔다.
- `company_type=JV`는 회사 자체가 JV 법인일 때만 사용한다. 배터리 셀 회사가 JV 공장에 가진
  생산능력은 회사 유형을 바꾸지 않고 `ownership_type=JV`로 표시한다.

### 5-5. 회사 데이터 예시

```jsonc
{
  "series_id": "p18_catl_ev_sales",
  "company_raw": "CATL",
  "company": "CATL",
  "company_type": "배터리셀",
  "facility_raw": null,
  "ownership_type": null,
  "jv_name_raw": null,
  "jv_partner_raw": null,
  "capacity_basis": null,
  "market": "EV",
  "application": "전체",
  "system_type": null,
  "geography_raw": "Global",
  "geography": "글로벌",
  "parent_geography": null,
  "geography_level": "글로벌",
  "metric": "판매량",
  "metric_raw": "출하량",
  "fy": 2026,
  "period": "2Q",
  "value": 96.5,
  "unit": "GWh",
  "raw_value": 96.5,
  "raw_unit": "GWh",
  "time_basis": "기간판매량",
  "as_of_date": null,
  "value_type": "실적",
  "basis": "글로벌 EV 배터리 출하량",
  "scope_note": null,
  "source_owner": "SNE Research",
  "source_kind": "조사기관",
  "extraction_method": "표",
  "value_precision": "정확",
  "page": 18
}
```

## 6. 생성할 인덱스와 Excel 뷰

인덱스 빌드는 아래 생성물을 만든다. 백필 전에는 헤더만 존재한다.

| 생성물 | 역할 |
|---|---|
| `index/market_series.csv` | 시장 관측값 전체. 연간 데이터가 기본 조회 대상 |
| `index/market_series_review.csv` | 자동 추측하지 않은 기존 수요 행과 검토 사유 |
| `index/company_volume_series.csv` | 회사별 판매량·생산능력. 분기와 연간 데이터 보존 |
| `index/demand_forecasts.csv` | 기존 대시보드 하위호환용 파생 인덱스 |

`market_series.csv`의 `origin_schema`와 `legacy_row`는 자동 이관 여부와 기존 배열의 행 번호를
추적하는 인덱스 메타데이터다. 명시적으로 작성한 새 행은 `origin_schema=market_series`, 기존
수요에서 파생한 행은 `origin_schema=demand_forecasts`로 구분한다.

Excel은 인덱스 구현과 백필 이후 별도 단계에서 생성한다.

- `Market_Raw`: 모든 시장 관측값
- `Market_Latest`: 동일 범위의 최신 관측값
- `Company_Raw`: 모든 회사 관측값
- `Company_Latest`: 동일 범위의 최신 관측값
- `Data_Dictionary`: 필드·통제어휘·환산 규칙
- `Sources`: 리포트·페이지·최초 출처
- `QA_Flags`: 단위·범위·중복·근사값 검토 대상

## 7. 검증 규칙

아래 위반은 신규 인제스트의 실패 조건으로 둔다.

1. 필수 필드 또는 페이지 누락.
2. 한 리포트 안의 `(series_id, fy, period)` 중복 또는 같은 `series_id`의 차원 불일치.
3. `market_series`와 `company_volume_series`의 필드 혼용.
4. ESS Application·시스템 형태 비표준.
5. 미국을 북미로 치환하거나 부모·자식 지역을 같은 시리즈에서 합산.
6. `실적`, `추정`, `가이던스`, `시나리오` 미구분.
7. GWh로 환산할 근거가 없는 회사 값을 임의 환산.
8. 회사 데이터에 금액 단위 입력.
9. 생산능력과 판매량의 합산 또는 동일 시리즈 사용.
10. `metric=판매량`인데 `metric_raw`가 없는 경우.
11. `extraction_method=차트`인데 `value_precision=정확`인 경우.
12. 최초 출처가 적혀 있는데 `source_kind=원천불명`인 경우.
13. 월간 수치를 `period=FY`로 저장한 경우.

## 8. 기존 데이터 이관 원칙

1. 기존 `demand_forecasts`는 자동 변환 대상으로 삼고 원본 행을 삭제하지 않는다.
2. 기존 `application=EV|ESS`는 새 `market`으로 이동한다.
3. ESS Application은 `basis`만으로 확정 가능한 경우에만 세분화한다. 애매하면 `전체`로 두고
   검토 플래그를 붙인다.
4. 기존 미국 데이터가 `북미`로 치환된 경우 `basis`의 `[원문지역:미국]` 표시로 복원한다.
5. 기존 `metric=실적치`는 자동 추측하지 않고 원문 맥락을 확인해 재분류한다.
6. 같은 키에 서로 다른 값이 있으면 삭제·평균하지 않고 `series_id`, `scope_note`, `page`로 분리한다.
7. 기존 구조에 숫자가 없는 회사 판매량·생산능력은 PDF의 관련 페이지만 선별 백필한다.
8. 표준 MD와 인덱스는 `.staging`을 수정한 뒤 `build_indexes.py`로 재생성한다. 생성물을
   직접 고치지 않는다.

자동 이관 코드는 기존 행을 다음처럼 처리한다.

- EV·ESS이고 지표·단위·지역·페이지·basis가 명확한 행만 `market_series.csv`에 넣는다.
- `실적치`, EV·ESS 외 application, 지원하지 않는 지표·단위, basis 누락은
  `market_series_review.csv`에 원문 값과 검토 사유를 남긴다.
- 표·차트 여부가 기존 구조에 명시되지 않은 값은 `extraction_method=원천불명`,
  `value_precision=근사`로 둔다.
- 월간·누적 값인데 정확한 `period`를 복원할 수 없는 행은 연간 값으로 만들지 않고 검토 대상으로 둔다.
- 자동 이관 행과 검토 행의 합계는 기존 행 수와 반드시 일치해야 한다.
- 2026-08-11 파일럿 기준 1,294행 중 765행은 자동 이관, 529행은 검토 대상으로 분류된다.

## 9. 이번 설계에서 제외하는 것

- PDF 전체 재인제스트
- 기존 1,294개 수요 데이터 백필
- 회사 금액·매출 데이터
- 환산 근거 없는 차량·셀 단위의 GWh 추정
- Excel 파일 생성
- 대시보드 변경

위 작업은 스키마·검증 코드가 확정된 뒤 순차적으로 진행한다.
