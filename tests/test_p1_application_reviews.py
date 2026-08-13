import csv
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEWS = os.path.join(ROOT, "projects", "market-data", "candidate_reviews.csv")
RECLASSIFICATION = os.path.join(
    ROOT, "projects", "market-data", "p1_market_reclassification.csv"
)


class P1ApplicationReviewsTest(unittest.TestCase):
    def test_all_additional_application_pages_are_reviewed_and_held(self):
        targets = {
            (
                "KB증권_LG에너지솔루션_2026년 미국 사업 ESS가 EV 미국 출하량 뛰어넘을 것_20260226.pdf",
                "3",
            ),
            ("LS증권_삼성SDI_상대적으로 양호한 포지션 대비 높은 가격_20260512.pdf", "1"),
            ("LS증권_삼성SDI_4월 EV향 data, 역성장 지속 우려_20260605.pdf", "9"),
            ("교보증권_LG에너지솔루션_1Q26 Preview 컨센서스 소폭 하회_20260330.pdf", "1"),
        }
        with open(REVIEWS, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        matched = {
            (row["source_file"], row["page"]): row
            for row in rows
            if (row["source_file"], row["page"]) in targets
        }

        self.assertEqual(targets, set(matched))
        self.assertTrue(all(row["review_status"] == "보류" for row in matched.values()))
        self.assertTrue(all(row["extraction_status"] == "미추출" for row in matched.values()))
        self.assertTrue(all(row["extracted_row_count"] == "0" for row in matched.values()))

    def test_every_selected_p1_page_has_a_review_decision(self):
        with open(RECLASSIFICATION, encoding="utf-8-sig", newline="") as handle:
            selected = {
                (row["source_group"], row["source_file"], row["page"])
                for row in csv.DictReader(handle)
                if row["reclassification"] in {"최신 유효", "추가 검토"}
            }
        with open(REVIEWS, encoding="utf-8-sig", newline="") as handle:
            reviewed = {
                (row["source_group"], row["source_file"], row["page"])
                for row in csv.DictReader(handle)
            }

        self.assertEqual(62, len(selected))
        self.assertEqual(set(), selected - reviewed)


if __name__ == "__main__":
    unittest.main()
