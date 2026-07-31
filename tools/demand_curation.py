# -*- coding: utf-8 -*-
"""수요 전망 시리즈 분류 — 비교가능성 큐레이션 (대시보드 v8).

배경: 산업리포트 파싱은 원문 표를 전부 수집한다(감사 추적). 그 결과 시장 전체
수요와 서브세그먼트(4680 전용, 소듐이온, 주택용 ESS 등)·시나리오·월간치·CAPA가
같은 차트에 섞여 증권사 View 비교가 불가능했다. 이 모듈이 각 (리포트×표) 시리즈를
분류해, 대시보드 기본 화면에는 '시장전체'만 표시한다.

분류 = 수기 오버라이드(최우선) → basis 텍스트 휴리스틱 규칙(위에서부터 첫 매치).
build_indexes.py 가 demand_forecasts.csv 에 series_class/series_label/scope_note
컬럼으로 기록하므로 신규 인제스트에도 자동 적용된다.

분류값:
  시장전체   해당 지역×용도 시장 전체의 연간 수요/침투율 전망 → 차트 기본 표시
  서브세그먼트 특정 기술·기업·부분시장(4680, 소듐이온, 주택용, 데이터센터향, 침투가능수요 등)
  시나리오   가정 기반 별도 추정(Model Q 시나리오, 연 30% 성장 가정시 등)
  월간·누적  연간이 아닌 월간/YTD 수치가 연도에 매핑된 행
  생산능력   수요가 아닌 CAPA/필요 생산능력 추정
  참고치    타사 컨센서스 인용, 신규/누적 기준 불명 등 하우스 자체 연간 전망이 아닌 값
"""
import re

MARKET = "시장전체"
SUB = "서브세그먼트"
SCEN = "시나리오"
NONANN = "월간·누적"
CAPA = "생산능력"
REF = "참고치"

# basis 정규식 → 분류. 순서 중요(첫 매치).
RULES = [
    (r"라인업|모델 종수", SUB),
    (r"CAPA|생산능력", CAPA),
    (r"4680|소듐이온|전고체|주택용|산업용|데이터센터|침투가능|케미스트리|LFP 배터리 침투율"
     r"|LFP 침투율|LFP 비중|삼원계|OEM|양극재|대당|증분 수요|태양광 발전 연계|로봇|수입액"
     r"|BBU|Cybertruck|UAM", SUB),
    (r"\d+월|누적 설치|1-2월|연간 누적|M/S", NONANN),
    (r"시나리오|가정시|BEV침투율100%|BEV 100%", SCEN),
    (r"컨센서스치|연구소|설치량 합계|설치량 전망\(20\d\dP\)", REF),
]

# 수치 아닌 보조 단위는 서브로(재료 톤수, 대당 kWh, 모델 종수 등)
SUB_UNITS = {"만톤", "톤", "kWh", "종", "대"}

# 수기 오버라이드: (report_id, region|None, application|None, metric|None, basis 접두|None) → 분류
# None = 해당 조건 무시. 위에서부터 첫 매치.
OVERRIDES = [
    # 삼성 2025-10 BNEF 표: 제목에 '데이터센터'가 들어가 휴리스틱이 오분류 → 수요량은 시장전체
    ("2025-10-23_삼성증권_산업", None, None, "수요량", "BNEF", MARKET),
    ("2025-10-23_삼성증권_산업", None, "ESS", "침투율", "BNEF", MARKET),
    # 같은 표의 'EV 침투율 77~87%'는 배터리 수요 내 EV 비중 — 신차 판매 침투율과 기준 상이
    ("2025-10-23_삼성증권_산업", None, "EV", "침투율", "BNEF", SUB),
]

# 같은 리포트 안 동일 개념 표 병합: (report_id, region, application, metric) → 시리즈 라벨.
# '시장전체' 행에만 적용 — 여러 basis 문자열로 쪼개진 동일 시리즈를 한 선으로 잇는다.
MERGE = {
    ("2025-03-21_삼성증권_산업", "글로벌", "EV", "수요량"): "글로벌 xEV 배터리 수요",
    ("2025-11-24_SK증권_산업", "글로벌", "EV", "수요량"): "EV 배터리 수요(글로벌)",
    ("2025-11-24_SK증권_산업", "글로벌", "ESS", "수요량"): "ESS 배터리 수요(글로벌)",
    ("2025-11-24_SK증권_산업", "북미", "ESS", "수요량"): "ESS 배터리 수요(미국)",
    ("2025-11-19_다올투자증권_산업", "글로벌", "EV", "수요량"): "글로벌 EV 배터리 TAM",
    ("2025-11-19_다올투자증권_산업", "글로벌", "EV", "침투율"): "글로벌 BEV 침투율",
    ("2023-05-23_SK증권_산업", "글로벌", "EV", "침투율"): "전기차 침투율 가정",
    ("2023-09-12_IBK투자증권_산업", "글로벌", "EV", "침투율"): "글로벌 EV 침투율",
}


def classify(report_id, region, application, metric, unit, basis):
    """→ {"cls": 분류, "label": 병합 라벨|None, "scope": 집계범위 주석|None}"""
    b = basis or ""
    cls = None
    for rid, reg, app, met, pre, c in OVERRIDES:
        if rid == report_id \
           and (reg is None or reg == region) \
           and (app is None or app == application) \
           and (met is None or met == metric) \
           and (pre is None or b.startswith(pre)):
            cls = c
            break
    if cls is None and metric == "침투율" and "xEV" in b:
        cls = SUB  # xEV(HEV 포함) 침투율은 BEV/BEV+PHEV 기준과 비교 불가
    if cls is None:
        for pat, c in RULES:
            if re.search(pat, b):
                cls = c
                break
    if cls is None and (unit or "") in SUB_UNITS:
        cls = SUB
    if cls is None:
        cls = MARKET
    label = MERGE.get((report_id, region, application, metric)) if cls == MARKET else None
    scope = "중국 제외" if "중국 제외" in b else None
    return {"cls": cls, "label": label, "scope": scope}
