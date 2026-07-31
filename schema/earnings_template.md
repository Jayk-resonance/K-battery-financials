# 실적·컨퍼런스콜 표준 스키마 (v1)

증권사 리포트(`schema/template.md`)와 회사 실적·컨퍼런스콜은 서로 다른 문서다.
회사 자료는 **회사×분기 1건**의 아래 패키지로 저장한다.

## 저장 경로와 생성물

| 구분 | 경로 | 직접 편집 |
|---|---|---|
| 원본 IR·스크립트 | `actuals/<원본 파일>` | 원본 보존 |
| 유일한 편집 원천 | `.staging/earnings_<FY>_<분기>_<회사>.json` | 예 |
| 표준 MD | `earnings/<FY>/<FY>_<분기>_<회사>.md` | 아니오 |
| 정량 실적 | `index/actuals.csv` | 아니오 |
| 변동 원인 | `index/drivers.csv` | 아니오 |
| 가이던스 | `index/guidance.csv` | 아니오 |
| 컨콜 Q&A | `index/call_qa.jsonl` | 아니오 |

예: `.staging/earnings_2026_2Q_LGES.json`의 `document_id`는
`2026_2Q_LGES`이며, `earnings/2026/2026_2Q_LGES.md`로 렌더된다.

## 신규 인제스트 JSON

```jsonc
{
  "schema_version": 1,
  "document_id": "2026_2Q_LGES",
  "document_type": "earnings_call",
  "company": "LGES",
  "fy": 2026,
  "period": "2Q",
  "announcement_date": "2026-07-30",
  "sources": [
    {"kind": "ir_deck", "file": "원본_IR.pdf"},
    {"kind": "call_script", "file": "원본_스크립트.pdf"}
  ],
  "actuals": [
    {
      "segment": "전사",
      "segment_std": "전사",
      "metric": "매출",
      "value": 0,
      "unit": "십억원",
      "ampc_basis": "incl",
      "source_file": "원본_IR.pdf",
      "page": 3
    }
  ],
  "drivers": [
    {
      "segment_std": "전사",
      "summary": "매출·이익 변동 원인을 사실과 회사 설명으로 요약",
      "source_file": "원본_IR.pdf",
      "page": 4
    }
  ],
  "guidance": [
    {
      "topic": "연간 매출 성장률",
      "horizon": "2026 FY",
      "direction": "유지",
      "value": 15,
      "value_max": 20,
      "unit": "%",
      "summary": "회사가 제시한 전제와 범위를 그대로 요약",
      "source_file": "원본_스크립트.pdf",
      "page": 6
    }
  ],
  "qa": [
    {
      "topic": "ESS 수익성",
      "question": "질문의 핵심을 한 문장으로 정리",
      "answer": "경영진 답변의 수치·조건·불확실성을 보존해 요약",
      "source_file": "원본_스크립트.pdf",
      "page": 12
    }
  ],
  "body": {
    "summary": "분기 핵심 결론",
    "actuals": "확정 실적 해설",
    "drivers": "사업부문별 변동 원인 해설",
    "ampc_oneoffs": "AMPC·보상금·손상차손·회계변경",
    "guidance": "가이던스의 조건과 전분기 대비 변화",
    "capex_capacity_orders": "CAPEX·생산능력·수주",
    "qa": "Q&A 전체의 핵심 쟁점",
    "risks": "회사 발언에서 확인되는 불확실성",
    "quotes": "검증 가능한 짧은 원문 인용과 페이지"
  }
}
```

## 강제 규칙

1. 신규 분기는 `actuals`와 `drivers` 키를 반드시 포함한다. 빈 배열은 허용하지만 키를 빼지 않는다.
2. 모든 정량값·변동 원인·가이던스·Q&A에는 `source_file`과 `page`를 남긴다.
3. 숫자는 회사 IR·보도자료를 우선하고, 컨콜은 원인·가이던스·Q&A를 보완한다.
4. `actuals`의 회사·연도·분기는 패키지 상단에서 상속하므로 행에 반복하지 않는다.
5. `guidance.value`와 `value_max`는 숫자만 쓴다. 정량화할 수 없으면 둘 다 `null`로 두고 `summary`에 원문 표현을 보존한다.
6. 질문과 답변은 분리한다. 질문을 추정해 만들었으면 정확한 원문 질문인 것처럼 따옴표를 붙이지 않는다.
7. 자료가 없으면 내용을 발명하지 말고 body에 `자료 없음` 또는 미수록 사유를 적는다.
8. `legacy_fact_ref`와 `citation_status: legacy_unpaged`는 기존 1Q26 회귀 자료 전용이다. 신규 인제스트에서 사용하지 않는다.

통제어휘:

- `sources.kind`: `ir_deck`, `press_release`, `call_script`, `prepared_remarks`, `transcript`
- `guidance.direction`: `유지`, `상향`, `하향`, `개선`, `악화`, `확대`, `축소`, `변경`, `흑자전환`, `목표`, `기타`
- `actuals.segment_std`, `ampc_basis`, 기간·단위 규칙은 `NORMALIZATION.md`를 따른다.

## 표준 MD 섹션 순서

1. 실적 핵심 요약
2. 확정 실적
3. 사업부문별 실적 및 변동 원인
4. AMPC·일회성 요인
5. 연간·분기 가이던스
6. CAPEX·생산능력·수주
7. 컨퍼런스콜 Q&A
8. 리스크 및 불확실성
9. 원문 인용

MD와 `index/*`는 `tools/build_indexes.py`가 생성한다. 생성물을 직접 고치지 않는다.
