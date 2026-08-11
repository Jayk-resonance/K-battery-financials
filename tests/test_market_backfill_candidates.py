import importlib.util
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "market_backfill_candidates", os.path.join(ROOT, "tools", "market_backfill_candidates.py")
)
CANDIDATES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATES)


class MarketBackfillCandidatesTest(unittest.TestCase):
    def test_market_page_is_selected(self):
        row = CANDIDATES.classify_page(
            "2030년 미국 데이터센터 Grid ESS 신규 설치용량은 300GWh로 전망"
        )
        self.assertEqual("시장", row["candidate_type"])
        self.assertIn("ESS", row["markets"])
        self.assertIn("데이터센터", row["applications"])

    def test_company_volume_page_is_selected(self):
        row = CANDIDATES.classify_page(
            "LG에너지솔루션 2027년 EV 배터리 생산능력 CAPA 300GWh 전망"
        )
        self.assertEqual("시장·회사", row["candidate_type"])
        self.assertIn("LG에너지솔루션", row["companies"])

    def test_ev_vehicle_sales_and_penetration_are_market_candidates(self):
        sales = CANDIDATES.classify_page(
            "2028년 미국 EV 판매대수는 1,500만대, 시장 침투율은 35% 전망"
        )
        self.assertEqual("시장", sales["candidate_type"])
        self.assertIn("만대", sales["units"])
        self.assertIn("%", sales["units"])

    def test_company_candidate_requires_energy_unit(self):
        self.assertIsNone(CANDIDATES.classify_page(
            "LG에너지솔루션 2027년 생산능력 300만대 전망"
        ))

    def test_incidental_company_on_power_demand_page_is_ignored(self):
        self.assertIsNone(CANDIDATES.classify_page(
            "Tesla 데이터센터 2028년 전력수요 450TWh, 총 전력수요 대비 8%"
        ))

    def test_contract_only_page_is_not_company_volume(self):
        self.assertIsNone(CANDIDATES.classify_page(
            "LG에너지솔루션 2027년 북미 EV 배터리 10GWh 공급계약 수주"
        ))

    def test_financial_page_without_volume_unit_is_ignored(self):
        self.assertIsNone(CANDIDATES.classify_page(
            "LG에너지솔루션 2027년 매출액 40조원, 영업이익 3조원 전망"
        ))


if __name__ == "__main__":
    unittest.main()
