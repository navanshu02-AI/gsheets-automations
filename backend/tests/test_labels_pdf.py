import re
import unittest

import pandas as pd

from app.labels import extract_label_rows, generate_labels_pdf, suggest_download_filename
from app.labels.render_labels_pdf import LANDSCAPE_4X6, PORTRAIT_4X6


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def _extract_media_boxes(pdf_bytes: bytes) -> list[tuple[float, float]]:
    matches = re.findall(
        rb"/MediaBox\s*\[\s*0\s+0\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)\s*\]",
        pdf_bytes,
    )
    return [(float(width), float(height)) for width, height in matches]


class LabelsPdfTests(unittest.TestCase):
    def test_extract_label_rows_maps_aliases(self):
        sheets = {
            "Sheet1": pd.DataFrame(
                {
                    "PO#": ["P-1"],
                    "Invoice#": ["INV-1"],
                    "Carton No": ["1"],
                    "SKU": ["A1"],
                    "Size": ["M"],
                    "Qty": [2],
                }
            )
        }
        rows = extract_label_rows(sheets)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["article_code"], "A1")
        self.assertEqual(rows[0]["qty"], "2")

    def test_extract_label_rows_raises_for_missing_columns(self):
        sheets = {
            "Sheet1": pd.DataFrame(
                {
                    "PO#": ["P-1"],
                    "Invoice#": ["INV-1"],
                    "Size": ["M"],
                    "Qty": [2],
                }
            )
        }
        with self.assertRaises(ValueError):
            extract_label_rows(sheets)

    def test_generate_labels_pdf_has_expected_page_count(self):
        rows = [
            {
                "po": "P-1",
                "invoice": "INV-1",
                "carton": "1",
                "article_code": "A1",
                "size": "M",
                "qty": "2",
            },
            {
                "po": "P-1",
                "invoice": "INV-1",
                "carton": "2",
                "article_code": "B1",
                "size": "L",
                "qty": "1",
            },
        ]
        pdf_bytes = generate_labels_pdf(rows, portrait=False, padding_in=0.25)
        self.assertEqual(_count_pdf_pages(pdf_bytes), 2)

    def test_generate_labels_pdf_has_exact_landscape_mediabox(self):
        rows = [
            {
                "po": "P-1",
                "invoice": "INV-1",
                "carton": "1",
                "article_code": "A1",
                "size": "M",
                "qty": "2",
            }
        ]
        pdf_bytes = generate_labels_pdf(rows, portrait=False, padding_in=0.25)
        media_boxes = _extract_media_boxes(pdf_bytes)
        self.assertTrue(any(box == LANDSCAPE_4X6 for box in media_boxes))

    def test_generate_labels_pdf_has_exact_portrait_mediabox(self):
        rows = [
            {
                "po": "P-1",
                "invoice": "INV-1",
                "carton": "1",
                "article_code": "A1",
                "size": "M",
                "qty": "2",
            }
        ]
        pdf_bytes = generate_labels_pdf(rows, portrait=True, padding_in=0.25)
        media_boxes = _extract_media_boxes(pdf_bytes)
        self.assertTrue(any(box == PORTRAIT_4X6 for box in media_boxes))

    def test_suggest_download_filename(self):
        rows = [
            {
                "po": "3100743891",
                "invoice": "CV/03/2025/013",
                "carton": "1",
                "article_code": "A1",
                "size": "M",
                "qty": "2",
            }
        ]
        filename = suggest_download_filename(rows)
        self.assertEqual(filename, "PO# 3100743891.pdf")


if __name__ == "__main__":
    unittest.main()
