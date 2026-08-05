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


if __name__ == "__main__":
    unittest.main()
