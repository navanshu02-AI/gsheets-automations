import re
import unittest

import pandas as pd

from app.labels import (
    extract_classic_sticker_rows,
    generate_classic_stickers_pdf,
    normalize_classic_sticker_value,
    parse_classic_sticker_config,
    resolve_classic_sticker_page_size,
    suggest_classic_sticker_filename,
)


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def _extract_media_boxes(pdf_bytes: bytes) -> list[tuple[float, float]]:
    matches = re.findall(
        rb"/MediaBox\s*\[\s*0\s+0\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)\s*\]",
        pdf_bytes,
    )
    return [(float(width), float(height)) for width, height in matches]


class ClassicStickersPdfTests(unittest.TestCase):
    def test_parse_classic_sticker_config(self):
        config = parse_classic_sticker_config(
            """
            {
              "sheet_name": "Sheet1",
              "label_size": "4x2",
              "padding_in": 0.1,
              "fields": [
                {"column": "Employee Code", "label": "Employee Code"},
                {"column": "NAME", "label": "NAME"}
              ]
            }
            """
        )

        self.assertEqual(config["sheet_name"], "Sheet1")
        self.assertEqual(config["label_size"], "4x2")
        self.assertEqual(config["padding_in"], 0.1)
        self.assertEqual(
            config["fields"],
            [
                {"column": "Employee Code", "label": "Employee Code"},
                {"column": "NAME", "label": "NAME"},
            ],
        )

    def test_parse_classic_sticker_config_rejects_invalid_json(self):
        with self.assertRaisesRegex(ValueError, "Invalid JSON config for classic stickers"):
            parse_classic_sticker_config("{")

    def test_parse_classic_sticker_config_rejects_empty_fields(self):
        with self.assertRaisesRegex(ValueError, "No fields selected for classic stickers"):
            parse_classic_sticker_config(
                """
                {
                  "sheet_name": "Sheet1",
                  "label_size": "4x2",
                  "padding_in": 0.1,
                  "fields": []
                }
                """
            )

    def test_parse_classic_sticker_config_rejects_invalid_label_size(self):
        with self.assertRaisesRegex(ValueError, "Unsupported classic sticker label size"):
            parse_classic_sticker_config(
                """
                {
                  "sheet_name": "Sheet1",
                  "label_size": "3x3",
                  "padding_in": 0.1,
                  "fields": [{"column": "NAME", "label": "NAME"}]
                }
                """
            )

    def test_normalize_classic_sticker_value_formats_scalars(self):
        self.assertEqual(normalize_classic_sticker_value(174826.0), "174826")
        self.assertEqual(normalize_classic_sticker_value("  Chennai  "), "Chennai")
        self.assertEqual(normalize_classic_sticker_value(None), "")

    def test_extract_classic_sticker_rows_preserves_order_and_skips_blank_rows(self):
        frame = pd.DataFrame(
            {
                "Employee Code": [174826, None],
                "NAME": ["Abdul Khader", ""],
                "SIZE": ["XL - 42", ""],
                "LOCATION": ["Chennai", ""],
                "KEY NUMBER": ["I252611073974", None],
            }
        )

        rows = extract_classic_sticker_rows(
            frame,
            [
                {"key": "Employee Code", "label": "Employee Code"},
                {"key": "NAME", "label": "NAME"},
                {"key": "SIZE", "label": "SIZE"},
                {"key": "LOCATION", "label": "LOCATION"},
                {"key": "KEY NUMBER", "label": "KEY NUMBER"},
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["lines"],
            [
                {"label": "Employee Code", "value": "174826"},
                {"label": "NAME", "value": "Abdul Khader"},
                {"label": "SIZE", "value": "XL - 42"},
                {"label": "LOCATION", "value": "Chennai"},
                {"label": "KEY NUMBER", "value": "I252611073974"},
            ],
        )

    def test_extract_classic_sticker_rows_raises_for_unmatched_fields(self):
        frame = pd.DataFrame({"Employee Code": [174826], "NAME": ["Abdul Khader"]})

        with self.assertRaises(ValueError):
            extract_classic_sticker_rows(frame, [{"key": "SIZE", "label": "SIZE"}])

    def test_resolve_classic_sticker_page_size(self):
        self.assertEqual(resolve_classic_sticker_page_size("2x2"), (144.0, 144.0))
        self.assertEqual(resolve_classic_sticker_page_size("4x2"), (288.0, 144.0))
        self.assertEqual(resolve_classic_sticker_page_size("4x4"), (288.0, 288.0))
        self.assertEqual(resolve_classic_sticker_page_size("4x6"), (288.0, 432.0))

    def test_generate_classic_stickers_pdf_has_one_page_per_row(self):
        sticker_rows = [
            {
                "lines": [
                    {"label": "Employee Code", "value": "174826"},
                    {"label": "NAME", "value": "Abdul Khader"},
                ]
            },
            {
                "lines": [
                    {"label": "Employee Code", "value": "174827"},
                    {"label": "NAME", "value": "Fathima"},
                ]
            },
        ]

        pdf_bytes = generate_classic_stickers_pdf(sticker_rows, label_size="4x2", padding_in=0.1)

        self.assertEqual(_count_pdf_pages(pdf_bytes), 2)
        self.assertTrue(any(box == (288.0, 144.0) for box in _extract_media_boxes(pdf_bytes)))

    def test_suggest_classic_sticker_filename(self):
        self.assertEqual(
            suggest_classic_sticker_filename("4x6"),
            "classic-stickers-4x6.pdf",
        )


if __name__ == "__main__":
    unittest.main()
