import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "build_indexes", os.path.join(ROOT, "tools", "build_indexes.py")
)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
MIGRATION_SPEC = importlib.util.spec_from_file_location(
    "market_migration", os.path.join(ROOT, "tools", "market_migration.py")
)
MARKET_MIGRATION = importlib.util.module_from_spec(MIGRATION_SPEC)
MIGRATION_SPEC.loader.exec_module(MARKET_MIGRATION)


def load_staging(name):
    with open(os.path.join(ROOT, ".staging", name), encoding="utf-8") as f:
        return json.load(f)


class EarningsPipelineTest(unittest.TestCase):
    def setUp(self):
        self.actuals_sets = []
        for name in ("actuals_LGES.json", "actuals_삼성SDI.json"):
            data = load_staging(name)
            data["_staging_file"] = name
            self.actuals_sets.append(data)
        self.lges = load_staging("earnings_2026_1Q_LGES.json")
        self.sdi = load_staging("earnings_2026_1Q_삼성SDI.json")
        self.lges_2q = load_staging("earnings_2026_2Q_LGES.json")
        self.sdi_2q = load_staging("earnings_2026_2Q_삼성SDI.json")

    def test_pilot_packages_pass_strict_validation(self):
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "build_indexes.py"),
             "--check-id", self.lges["document_id"],
             "--check-id", self.sdi["document_id"],
             "--check-id", self.lges_2q["document_id"],
             "--check-id", self.sdi_2q["document_id"]],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("대상 경고 0건", result.stdout)

    def test_legacy_reference_reuses_existing_facts_without_copying(self):
        self.assertEqual(len(BUILD.earnings_fact_rows(self.lges, self.actuals_sets, "actuals")), 8)
        self.assertEqual(len(BUILD.earnings_fact_rows(self.lges, self.actuals_sets, "drivers")), 1)
        self.assertEqual(len(BUILD.earnings_fact_rows(self.sdi, self.actuals_sets, "actuals")), 8)
        self.assertEqual(len(BUILD.earnings_fact_rows(self.sdi, self.actuals_sets, "drivers")), 2)

    def test_standard_package_values_override_legacy_reference(self):
        package = dict(self.lges)
        package["actuals"] = [{"metric": "매출", "value": 1}]
        rows = BUILD.earnings_fact_rows(package, self.actuals_sets, "actuals")
        self.assertEqual(rows, package["actuals"])

    def test_reference_key_figures_are_unchanged(self):
        lges_rows = BUILD.earnings_fact_rows(self.lges, self.actuals_sets, "actuals")
        lges = {(row["segment_std"], row["metric"]): row["value"] for row in lges_rows}
        self.assertEqual(lges[("전사", "매출")], 6555)
        self.assertEqual(lges[("전사", "영업이익")], -208)
        self.assertEqual(lges[("전사", "AMPC")], 190)

        sdi_rows = BUILD.earnings_fact_rows(self.sdi, self.actuals_sets, "actuals")
        sdi = {(row["segment_std"], row["metric"]): row["value"] for row in sdi_rows}
        self.assertEqual(sdi[("전사", "매출")], 3576.4)
        self.assertEqual(sdi[("전사", "영업이익")], -155.6)
        self.assertEqual(sdi[("배터리합계", "매출")], 3354.4)

        self.assertEqual(len(self.lges["guidance"]), 4)
        self.assertEqual(len(self.lges["qa"]), 6)
        self.assertEqual(self.sdi["guidance"], [])
        self.assertEqual(self.sdi["qa"], [])

    def test_second_quarter_key_figures_and_call_counts(self):
        lges = {(row["segment_std"], row["metric"]): row["value"]
                for row in self.lges_2q["actuals"]}
        self.assertEqual(lges[("전사", "매출")], 7560)
        self.assertEqual(lges[("전사", "영업이익")], 113)
        self.assertEqual(lges[("전사", "영업이익_AMPC제외")], -128)
        self.assertEqual(lges[("전사", "AMPC")], 241)
        self.assertEqual(len(self.lges_2q["guidance"]), 5)
        self.assertEqual(len(self.lges_2q["qa"]), 7)

        sdi = {(row["segment_std"], row["metric"]): row["value"]
               for row in self.sdi_2q["actuals"]}
        self.assertEqual(sdi[("전사", "매출")], 3768.8)
        self.assertEqual(sdi[("전사", "영업이익")], 203.8)
        self.assertEqual(sdi[("배터리합계", "매출")], 3519.0)
        self.assertEqual(sdi[("배터리합계", "영업이익")], 159.3)
        self.assertEqual(len(self.sdi_2q["guidance"]), 4)
        self.assertEqual(self.sdi_2q["qa"], [])

    def test_rendered_markdown_has_fixed_section_order(self):
        rendered = BUILD.render_earnings_md(self.lges, self.actuals_sets)
        headings = [
            "## 실적 핵심 요약", "## 확정 실적", "## 사업부문별 실적 및 변동 원인",
            "## AMPC·일회성 요인", "## 연간·분기 가이던스",
            "## CAPEX·생산능력·수주", "## 컨퍼런스콜 Q&A",
            "## 리스크 및 불확실성", "## 원문 인용"
        ]
        positions = [rendered.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("6,555", rendered.replace("6555", "6,555"))

    def test_strict_validation_rejects_incomplete_qna(self):
        package = json.loads(json.dumps(self.lges))
        del package["qa"][0]["answer"]
        BUILD.warnings.clear()
        BUILD.validate_earnings(package, "earnings_2026_1Q_LGES.json")
        target = BUILD.warnings_for([package["document_id"]])
        self.assertTrue(any("qa 필수 필드 누락: answer" in warning for warning in target))

    def test_dashboard_selects_next_unreported_quarter(self):
        path = os.path.join(ROOT, "projects", "dashboard", "dashboard_template.html")
        with open(path, encoding="utf-8") as f:
            template = f.read()
        self.assertIn('f6Head(sel.f6,isQ?"quarter":"annual")', template)
        self.assertIn('outlierPanel(card,sel.f6,"quarter")', template)
        self.assertIn('const qt=f6Target("quarter")', template)
        self.assertNotIn('outlierPanel(card,sel.f6,"2Q")', template)

        with open(os.path.join(ROOT, "projects", "dashboard", "data.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        outliers = data["f5_outliers"]
        quarter = outliers["analysis_targets"]["quarter"]
        annual = outliers["analysis_targets"]["annual"]
        self.assertEqual({"fy": 2026, "period": "3Q"}, quarter)
        self.assertEqual({"fy": 2026, "period": "FY"}, annual)
        groups = {(x["company"], x["fy"], x["period"])
                  for x in outliers["estimate_outliers"]}
        for company in ("LGES", "삼성SDI", "SK온"):
            self.assertIn((company, quarter["fy"], quarter["period"]), groups)
            self.assertIn((company, annual["fy"], annual["period"]), groups)

    def test_outlier_interpretation_explains_strategic_disagreement(self):
        with open(os.path.join(ROOT, "projects", "dashboard", "data.json"),
                  encoding="utf-8") as f:
            groups = json.load(f)["f5_outliers"]["estimate_outliers"]
        by_key = {(g["company"], g["fy"], g["period"]): g for g in groups}

        expected = {
            ("LGES", 2026, "3Q"): "흑자 유지",
            ("삼성SDI", 2026, "3Q"): "흑자·적자 방향 자체",
            ("SK온", 2026, "3Q"): "적자 지속",
        }
        for key, phrase in expected.items():
            readout = by_key[key]["interpretation"]
            self.assertIn(phrase, readout["conclusion"])
            self.assertGreater(readout["spread"], 0)
            self.assertTrue(readout["low_driver"]["summary"])
            self.assertTrue(readout["high_driver"]["summary"])

    def test_dashboard_uses_plain_language_navigation_and_help(self):
        path = os.path.join(ROOT, "projects", "dashboard", "dashboard_template.html")
        with open(path, encoding="utf-8") as f:
            template = f.read()
        for label in ("② 전망 분포·이견", "③ 과거 추정 오차", "④ 이슈별 3사 평가",
                      "⑤ 증권사 전망 변화", "⑥ 산업 수요 전망"):
            self.assertIn(label, template)
        self.assertIn("const TERM_HELP", template)
        self.assertIn("그래서 중요한 점", template)
        self.assertIn("g.interpretation", template)
        self.assertNotIn("const F6GAP", template)

    def test_mobile_navigation_exposes_all_tabs_and_centers_selection(self):
        path = os.path.join(ROOT, "projects", "dashboard", "dashboard_template.html")
        with open(path, encoding="utf-8") as f:
            template = f.read()
        for marker in ("navMenuToggle", "navPrev", "navNext", "navPosition"):
            self.assertIn(marker, template)
        self.assertIn("전체 탭", template)
        self.assertIn("scrollIntoView", template)
        self.assertIn("updateNavEdges", template)
        self.assertIn("centerNavOnRender", template)
        self.assertIn('aria-label="이전 탭 보기"', template)
        self.assertIn('aria-label="다음 탭 보기"', template)

    def test_market_and_company_series_pass_strict_validation(self):
        market = {
            "series_id": "p55_us_ess_datacenter", "market": "ESS",
            "application": "데이터센터", "system_type": "UPS",
            "geography_raw": "US", "geography": "미국",
            "parent_geography": "북미", "geography_level": "국가",
            "metric": "수요량", "fy": 2030, "period": "FY",
            "value": 35.0, "value_prev": None, "unit": "GWh",
            "value_type": "추정", "series_class": "서브세그먼트",
            "subsegment_raw": "데이터센터 UPS용",
            "basis": "미국 데이터센터 UPS 배터리 수요", "scope_note": None,
            "source_owner": "BNEF", "source_kind": "조사기관",
            "extraction_method": "표", "value_precision": "정확", "page": 55
        }
        company = {
            "series_id": "p18_catl_ev_sales", "company_raw": "CATL",
            "company": "CATL", "company_type": "배터리셀", "market": "EV",
            "application": "전체", "system_type": None,
            "geography_raw": "Global", "geography": "글로벌",
            "parent_geography": None, "geography_level": "글로벌",
            "metric": "판매량", "metric_raw": "출하량",
            "fy": 2026, "period": "2Q", "value": 96.5, "unit": "GWh",
            "raw_value": 96.5, "raw_unit": "GWh", "time_basis": "기간판매량",
            "as_of_date": None, "value_type": "실적",
            "basis": "글로벌 EV 배터리 출하량", "scope_note": None,
            "source_owner": "SNE Research", "source_kind": "조사기관",
            "extraction_method": "표", "value_precision": "정확", "page": 18
        }
        BUILD.warnings.clear()
        BUILD.validate_market_series("pilot", [market])
        BUILD.validate_company_volume_series("pilot", [company])
        self.assertEqual([], BUILD.warnings)

    def test_market_and_company_series_reject_unsafe_normalization(self):
        market = {
            "series_id": "bad_market", "market": "ESS", "application": "통신",
            "system_type": "기타", "geography_raw": "미국", "geography": "북미",
            "parent_geography": "글로벌", "geography_level": "권역",
            "metric": "수요량", "fy": 2030, "period": "FY", "value": 1,
            "unit": "GWh", "value_type": "추정", "series_class": "시장전체",
            "basis": "", "source_kind": "원천불명", "extraction_method": "차트",
            "value_precision": "정확", "page": None
        }
        company = {
            "series_id": "bad_company", "company_raw": "CATL", "company": "CATL",
            "company_type": "배터리셀", "market": "EV", "application": "전체",
            "system_type": None, "geography_raw": "Global", "geography": "글로벌",
            "parent_geography": None, "geography_level": "글로벌",
            "metric": "판매량", "metric_raw": None, "fy": 2026, "period": "2Q",
            "value": 100, "unit": "억원", "raw_value": 100, "raw_unit": "억원",
            "time_basis": "기간판매량", "value_type": "실적", "basis": "금액",
            "source_kind": "원천불명", "extraction_method": "표",
            "value_precision": "정확", "page": 1
        }
        BUILD.warnings.clear()
        BUILD.validate_market_series("bad", [market])
        BUILD.validate_company_volume_series("bad", [company])
        joined = "\n".join(BUILD.warnings)
        for phrase in ("application 비표준", "system_type 비표준", "미국을 북미로 치환",
                       "원문 페이지 누락", "차트 판독값", "metric_raw 누락",
                       "회사 단위 비표준", "회사 금액 단위 금지"):
            self.assertIn(phrase, joined)

    def test_series_id_connects_periods_but_rejects_duplicate_observation(self):
        base = {
            "series_id": "connected", "market": "EV", "application": "전체",
            "system_type": None, "geography_raw": "Global", "geography": "글로벌",
            "parent_geography": None, "geography_level": "글로벌",
            "metric": "수요량", "period": "FY", "value": 10, "unit": "GWh",
            "value_type": "추정", "series_class": "시장전체", "basis": "전망",
            "source_kind": "증권사추정", "extraction_method": "표",
            "value_precision": "정확", "page": 1
        }
        rows = [dict(base, fy=2026), dict(base, fy=2027, value=12),
                dict(base, fy=2027, value=13)]
        BUILD.warnings.clear()
        BUILD.validate_market_series("series", rows)
        joined = "\n".join(BUILD.warnings)
        self.assertEqual(1, joined.count("동일 기간 중복"))
        self.assertNotIn("series_id 중복", joined)

    def test_market_validator_rejects_monthly_value_labeled_as_fy(self):
        row = {
            "series_id": "monthly_as_fy", "market": "EV", "application": "전체",
            "system_type": None, "geography_raw": "미국", "geography": "미국",
            "parent_geography": "북미", "geography_level": "국가",
            "metric": "판매대수", "fy": 2026, "period": "FY", "value": 81,
            "unit": "천대", "value_type": "실적", "series_class": "월간·누적",
            "subsegment_raw": "BEV", "basis": "2026년 5월 미국 BEV 판매량",
            "source_kind": "조사기관", "extraction_method": "본문",
            "value_precision": "정확", "page": 10,
        }
        BUILD.warnings.clear()
        BUILD.validate_market_series("monthly", [row])
        self.assertIn("월간 수치를 period=FY로 저장 금지", "\n".join(BUILD.warnings))

    def test_market_company_index_writer_creates_separate_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            BUILD.write_market_company_indexes(tmp, [])
            market_path = os.path.join(tmp, "market_series.csv")
            review_path = os.path.join(tmp, "market_series_review.csv")
            company_path = os.path.join(tmp, "company_volume_series.csv")
            self.assertTrue(os.path.exists(market_path))
            self.assertTrue(os.path.exists(review_path))
            self.assertTrue(os.path.exists(company_path))
            with open(market_path, encoding="utf-8") as f:
                self.assertIn("market,application,system_type", f.readline())
            with open(company_path, encoding="utf-8") as f:
                header = f.readline()
            self.assertIn("metric,metric_raw", header)
            self.assertIn("raw_value,raw_unit", header)

    def test_quant_backfill_merges_by_report_id_without_leaking_id_into_row(self):
        reports = [{"report_id": "pilot"}]
        backfill = {
            "company_volume_series": [
                {"report_id": "pilot", "series_id": "capacity", "value": 50}
            ]
        }
        BUILD.warnings.clear()
        BUILD.merge_quant_backfill(reports, backfill)
        self.assertEqual(
            [{"series_id": "capacity", "value": 50}],
            reports[0]["company_volume_series"],
        )

    def test_legacy_market_migration_connects_safe_annual_series(self):
        report = {
            "report_id": "pilot", "date": "2026-07-31", "house": "테스트",
            "demand_forecasts": [
                {"region": "미국", "application": "ESS", "metric": "수요량",
                 "fy": 2027, "value": 12, "value_prev": None, "unit": "GWh",
                 "basis": "미국 데이터센터 UPS 수요 전망", "page": 5},
                {"region": "미국", "application": "ESS", "metric": "수요량",
                 "fy": 2030, "value": 30, "value_prev": None, "unit": "GWh",
                 "basis": "미국 데이터센터 UPS 수요 전망", "page": 5},
            ]
        }
        migrated, review = MARKET_MIGRATION.migrate_legacy_demands(report)
        self.assertEqual([], review)
        self.assertEqual(2, len(migrated))
        self.assertEqual(1, len({row["series_id"] for row in migrated}))
        self.assertTrue(all(row["geography"] == "미국" for row in migrated))
        self.assertTrue(all(row["parent_geography"] == "북미" for row in migrated))
        self.assertTrue(all(row["application"] == "데이터센터" for row in migrated))
        self.assertTrue(all(row["system_type"] == "UPS" for row in migrated))
        self.assertTrue(all(row["extraction_method"] == "원천불명" for row in migrated))

    def test_legacy_market_migration_preserves_installation_and_ev_subsegment(self):
        report = {
            "report_id": "dimensions", "date": "2026-07-31", "house": "테스트",
            "demand_forecasts": [
                {"region": "글로벌", "application": "ESS", "metric": "수요량",
                 "fy": 2030, "value": 300, "value_prev": None, "unit": "GWh",
                 "basis": "글로벌 BESS 신규 설치용량 전망 차트", "page": 8},
                {"region": "미국", "application": "EV", "metric": "판매대수",
                 "fy": 2027, "value": 2000, "value_prev": None, "unit": "천대",
                 "basis": "미국 BEV 판매대수 전망 표", "page": 9},
            ]
        }
        migrated, review = MARKET_MIGRATION.migrate_legacy_demands(report)
        self.assertEqual([], review)
        self.assertEqual("설치에너지", migrated[0]["metric"])
        self.assertEqual("차트", migrated[0]["extraction_method"])
        self.assertEqual("BEV", migrated[1]["subsegment_raw"])
        self.assertEqual("서브세그먼트", migrated[1]["series_class"])

    def test_legacy_market_migration_does_not_label_monthly_data_as_fy(self):
        report = {
            "report_id": "monthly", "date": "2026-06-08", "house": "테스트",
            "demand_forecasts": [
                {"region": "미국", "application": "EV", "metric": "판매대수",
                 "fy": 2026, "value": 81, "value_prev": None, "unit": "천대",
                 "basis": "2026년 5월 미국 BEV 판매량", "page": 10},
            ]
        }
        migrated, review = MARKET_MIGRATION.migrate_legacy_demands(report)
        self.assertEqual([], migrated)
        self.assertEqual(1, len(review))
        self.assertIn("월간·누적 자료는 period 재확인 필요", review[0]["review_reasons"])

    def test_legacy_market_migration_routes_ambiguous_rows_to_review(self):
        report = {
            "report_id": "review", "date": "2026-07-31", "house": "테스트",
            "demand_forecasts": [
                {"region": "글로벌", "application": "EV", "metric": "실적치",
                 "fy": 2025, "value": 100, "value_prev": None, "unit": "GWh",
                 "basis": "글로벌 EV 배터리", "page": 2},
                {"region": "글로벌", "application": "로봇", "metric": "수요량",
                 "fy": 2030, "value": 10, "value_prev": None, "unit": "GWh",
                 "basis": "휴머노이드 로봇 수요", "page": 3},
            ]
        }
        migrated, review = MARKET_MIGRATION.migrate_legacy_demands(report)
        self.assertEqual([], migrated)
        self.assertEqual(2, len(review))
        reasons = "\n".join(row["review_reasons"] for row in review)
        self.assertIn("실적치는 원문 지표 재확인 필요", reasons)
        self.assertIn("EV·ESS 외 application: 로봇", reasons)

    def test_legacy_market_migration_does_not_average_duplicate_values(self):
        base = {"region": "글로벌", "application": "EV", "metric": "수요량",
                "fy": 2030, "value_prev": None, "unit": "GWh",
                "basis": "글로벌 EV 배터리 수요", "page": 7}
        report = {
            "report_id": "duplicate", "date": "2026-07-31", "house": "테스트",
            "demand_forecasts": [dict(base, value=100), dict(base, value=120)]
        }
        migrated, review = MARKET_MIGRATION.migrate_legacy_demands(report)
        self.assertEqual([], migrated)
        self.assertEqual(2, len(review))
        self.assertTrue(all(row["review_reasons"] == "같은 시리즈·기간에 복수 값 존재"
                            for row in review))

    def test_all_legacy_demand_rows_are_reconciled_without_guessing(self):
        migrated_total = review_total = source_total = 0
        for name in os.listdir(os.path.join(ROOT, ".staging")):
            if not name.endswith(".json") or name == "manifest.json":
                continue
            data = load_staging(name)
            if not isinstance(data, dict) or not data.get("report_id"):
                continue
            migrated, review = MARKET_MIGRATION.migrate_legacy_demands(data)
            source_total += len(data.get("demand_forecasts", []) or [])
            migrated_total += len(migrated)
            review_total += len(review)
            BUILD.warnings.clear()
            BUILD.validate_market_series(data["report_id"], migrated)
            self.assertEqual([], BUILD.warnings, data["report_id"])
        self.assertEqual(1294, source_total)
        self.assertEqual(765, migrated_total)
        self.assertEqual(529, review_total)
        self.assertEqual(source_total, migrated_total + review_total)

    def test_normalized_op_waterfall_uses_broker_ranges_without_double_counting(self):
        with open(os.path.join(ROOT, "projects", "dashboard", "data.json"),
                  encoding="utf-8") as f:
            waterfall = json.load(f)["f1_quarterly"]["normalized_waterfall"]
        companies = waterfall["companies"]
        self.assertEqual({"LGES", "삼성SDI", "SK온"}, set(companies))
        expected = {
            "LGES": (113.0, -228.0),
            "삼성SDI": (203.8, -103.9),
            "SK온": (821.8, -308.0),
        }
        for company, (reported, normalized) in expected.items():
            self.assertEqual(reported, companies[company]["reported"]["value"])
            self.assertEqual(normalized, companies[company]["normalized"]["median"])
            self.assertLessEqual(companies[company]["normalized"]["min"], normalized)
            self.assertGreaterEqual(companies[company]["normalized"]["max"], normalized)
            for component in companies[company]["components"]:
                houses = [source["house"] for source in component["sources"]
                          if source["house"] != "회사 IR"]
                self.assertEqual(len(houses), len(set(houses)))

        sdi = {row["key"]: row for row in companies["삼성SDI"]["components"]}
        self.assertEqual((190.0, 200.0, 5),
                         (sdi["tariff_refund"]["min"], sdi["tariff_refund"]["max"],
                          sdi["tariff_refund"]["n"]))
        skon_unquantified = companies["SK온"]["unquantified"]
        self.assertEqual(["tariff_refund"], [row["key"] for row in skon_unquantified])
        self.assertNotIn("tariff_refund",
                         [row["key"] for row in companies["SK온"]["components"]])

    def test_normalized_waterfall_is_rendered_with_estimate_warning(self):
        path = os.path.join(ROOT, "projects", "dashboard", "dashboard_template.html")
        with open(path, encoding="utf-8") as f:
            template = f.read()
        self.assertIn("normalizedWaterfallCard(v)", template)
        self.assertIn("증권사 추정 기반 분석", template)
        self.assertIn("회계상 조정 영업이익이 아닙니다", template)
        self.assertIn("중복 차감 방지", template)

    def test_segment_charts_use_latest_actual_quarter_and_summary(self):
        with open(os.path.join(ROOT, "projects", "dashboard", "data.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        f1 = data["f1_quarterly"]
        for company in ("LGES", "삼성SDI", "SK온"):
            latest = f1["segment_latest"][company]
            self.assertEqual((latest["fy"], latest["period"]), (2026, "2Q"))
            self.assertTrue(latest["segment_revenue_summary"])
            self.assertTrue(latest["segment_operating_profit_summary"])

        actuals = f1["actuals_grid"]
        self.assertEqual(actuals["삼성SDI|2026|2Q"]["배터리합계|매출|na"], 3519.0)
        self.assertEqual(actuals["삼성SDI|2026|2Q"]["배터리합계|영업이익|incl"], 159.3)
        self.assertEqual(actuals["SK온|2026|2Q"]["배터리합계|매출|incl_unknown"], 2946.0)
        self.assertEqual(actuals["SK온|2026|2Q"]["배터리합계|영업이익|incl_unknown"], 821.8)

        path = os.path.join(ROOT, "projects", "dashboard", "dashboard_template.html")
        with open(path, encoding="utf-8") as f:
            template = f.read()
        self.assertIn("segmentActual", template)
        self.assertIn("segment_latest", template)
        self.assertIn('mkpts(totSeg,"영업이익(incl)","영업이익",true)', template)
        self.assertNotIn('점선 = 전망(26.2Q~', template)

    def test_qoq_supplements_cover_both_2026_quarters(self):
        with open(os.path.join(ROOT, "projects", "dashboard", "qoq_supplements.json"),
                  encoding="utf-8") as f:
            supplements = json.load(f)["companies"]
        required = {"headline", "operating_events", "recurring_policy_events",
                    "non_recurring_events", "normalized_view", "sources"}
        for company in ("LGES", "삼성SDI", "SK온"):
            self.assertEqual({"2026-1Q", "2026-2Q"}, set(supplements[company]))
            for quarter in supplements[company].values():
                self.assertTrue(required.issubset(quarter))
                self.assertTrue(quarter["operating_events"])
                self.assertTrue(quarter["sources"])
        sdi_2q = supplements["삼성SDI"]["2026-2Q"]
        self.assertIn("관세환급", " ".join(sdi_2q["non_recurring_events"]))
        self.assertIn("증권사 추정", {source["type"] for source in sdi_2q["sources"]})

    def test_tariff_refund_backfill_is_limited_to_22_reports(self):
        expected = {
            "2026-06-25_NH투자증권_LGES", "2026-06-25_NH투자증권_삼성SDI",
            "2026-06-26_미래에셋증권_삼성SDI", "2026-06-30_iM증권_LGES",
            "2026-07-30_KB증권_LGES", "2026-07-30_삼성증권_LGES",
            "2026-07-31_DB증권_삼성SDI", "2026-07-31_DS투자증권_LGES",
            "2026-07-31_IBK투자증권_SK온", "2026-07-31_IBK투자증권_삼성SDI",
            "2026-07-31_LS증권_삼성SDI", "2026-07-31_NH투자증권_삼성SDI",
            "2026-07-31_iM증권_삼성SDI", "2026-07-31_대신증권_삼성SDI",
            "2026-07-31_미래에셋증권_삼성SDI", "2026-07-31_삼성증권_삼성SDI",
            "2026-07-31_신영증권_삼성SDI", "2026-07-31_신한투자증권_LGES",
            "2026-07-31_신한투자증권_삼성SDI", "2026-07-31_키움증권_삼성SDI",
            "2026-07-31_하나증권_LGES", "2026-07-31_하나증권_삼성SDI"
        }
        tagged = {}
        old_refund_rows = []
        staging = os.path.join(ROOT, ".staging")
        for name in os.listdir(staging):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(staging, name), encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            report_id = data.get("report_id")
            if not report_id:
                continue
            refund_rows = [row for row in data.get("stances", [])
                           if row.get("issue") == "관세환급"]
            if refund_rows:
                tagged[report_id] = refund_rows
            old_refund_rows.extend(
                (report_id, row) for row in data.get("stances", [])
                if row.get("issue") == "관세"
                and any(word in row.get("summary", "") for word in ("환급", "환입"))
            )
        self.assertEqual(expected, set(tagged))
        self.assertTrue(all(len(rows) == 1 for rows in tagged.values()))
        self.assertEqual([], old_refund_rows)

    def test_accuracy_uses_one_latest_preview_per_house(self):
        with open(os.path.join(ROOT, "projects", "dashboard", "data.json"),
                  encoding="utf-8") as f:
            events = json.load(f)["f4_accuracy"]["events"]
        q2_expected = {"LGES": 22, "삼성SDI": 10, "SK온": 10}
        for event in events:
            houses = [pred["house"] for pred in event["preds"]]
            self.assertEqual(len(houses), len(set(houses)))
            self.assertEqual(event["n_houses"], len(houses))
            self.assertTrue(all(event["preview_start"] <= pred["date"] < event["announce_date"]
                                for pred in event["preds"]))
            self.assertTrue(all(pred["op_est"] is not None for pred in event["preds"]))
            if event["period"] == "2Q":
                self.assertEqual(q2_expected[event["company"]], event["n_houses"])


if __name__ == "__main__":
    unittest.main()
