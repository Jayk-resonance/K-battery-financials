import importlib.util
import json
import os
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "build_indexes", os.path.join(ROOT, "tools", "build_indexes.py")
)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


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
