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
    validate_classic_sticker_padding,
)

try:
    from fastapi.testclient import TestClient
except (ModuleNotFoundError, RuntimeError):
    TestClient = None
else:
    from app.main import app


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def _extract_media_boxes(pdf_bytes: bytes) -> list[tuple[float, float]]:
    matches = re.findall(
        rb"/MediaBox\s*\[\s*0\s+0\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)\s*\]",
        pdf_bytes,
    )
    return [(float(width), float(height)) for width, height in matches]


class ClassicStickersPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app) if TestClient is not None else None

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
                {"column": "Employee Code", "label": "Employee Code", "value": ""},
                {"column": "NAME", "label": "NAME", "value": ""},
            ],
        )

    def test_parse_classic_sticker_config_preserves_sheet_name_spacing(self):
        config = parse_classic_sticker_config(
            """
            {
              "sheet_name": "Final ",
              "label_size": "4x2",
              "padding_in": 0.1,
              "fields": [{"column": "Employee Code", "label": "Employee Code"}]
            }
            """
        )

        self.assertEqual(config["sheet_name"], "Final ")

    def test_parse_classic_sticker_config_defaults_blank_label_to_column(self):
        config = parse_classic_sticker_config(
            """
            {
              "sheet_name": "Sheet1",
              "label_size": "4x2",
              "padding_in": 0.1,
              "fields": [
                {"column": "Employee Code", "label": ""}
              ]
            }
            """
        )

        self.assertEqual(
            config["fields"],
            [{"column": "Employee Code", "label": "Employee Code", "value": ""}],
        )

    def test_parse_classic_sticker_config_rejects_invalid_json(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            parse_classic_sticker_config("{")

    def test_parse_classic_sticker_config_rejects_empty_fields(self):
        with self.assertRaisesRegex(ValueError, "Select at least one field"):
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
        with self.assertRaisesRegex(ValueError, "Invalid label size"):
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

    def test_parse_classic_sticker_config_allows_custom_field_without_column(self):
        config = parse_classic_sticker_config(
            """
            {
              "sheet_name": "Sheet1",
              "label_size": "4x2",
              "padding_in": 0.1,
              "fields": [{"column": "", "label": "Box No", "value": ""}]
            }
            """
        )

        self.assertEqual(
            config["fields"],
            [{"column": "", "label": "Box No", "value": ""}],
        )

    def test_parse_classic_sticker_config_rejects_immediate_duplicate_field(self):
        with self.assertRaisesRegex(ValueError, "accidental duplicate"):
            parse_classic_sticker_config(
                """
                {
                  "sheet_name": "Sheet1",
                  "label_size": "4x2",
                  "padding_in": 0.1,
                  "fields": [
                    {"column": "NAME", "label": "NAME"},
                    {"column": "NAME", "label": "NAME"}
                  ]
                }
                """
            )

    def test_parse_classic_sticker_config_allows_non_adjacent_duplicate_field(self):
        config = parse_classic_sticker_config(
            """
            {
              "sheet_name": "Sheet1",
              "label_size": "4x2",
              "padding_in": 0.1,
              "fields": [
                {"column": "NAME", "label": "NAME"},
                {"column": "SIZE", "label": "SIZE"},
                {"column": "NAME", "label": "Repeat Name"}
              ]
            }
            """
        )

        self.assertEqual(len(config["fields"]), 3)

    def test_validate_classic_sticker_padding_rejects_too_large_padding(self):
        with self.assertRaisesRegex(ValueError, "too large"):
            validate_classic_sticker_padding("2x2", 1.1)

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

    def test_extract_classic_sticker_rows_skips_blank_values(self):
        frame = pd.DataFrame(
            {
                "Employee Code": [174826],
                "NAME": ["Abdul Khader"],
                "SIZE": [None],
                "LOCATION": ["  Chennai  "],
            }
        )

        rows = extract_classic_sticker_rows(
            frame,
            [
                {"column": "Employee Code", "label": "Employee Code"},
                {"column": "NAME", "label": "NAME"},
                {"column": "SIZE", "label": "SIZE"},
                {"column": "LOCATION", "label": "LOCATION"},
            ],
        )

        self.assertEqual(
            rows[0]["lines"],
            [
                {"label": "Employee Code", "value": "174826"},
                {"label": "NAME", "value": "Abdul Khader"},
                {"label": "LOCATION", "value": "Chennai"},
            ],
        )

    def test_extract_classic_sticker_rows_includes_custom_static_field(self):
        frame = pd.DataFrame({"NAME": ["Abdul Khader"]})

        rows = extract_classic_sticker_rows(
            frame,
            [
                {"column": "NAME", "label": "NAME"},
                {"column": "", "label": "Box No", "value": ""},
            ],
        )

        self.assertEqual(
            rows[0]["lines"],
            [
                {"label": "NAME", "value": "Abdul Khader"},
                {"label": "Box No", "value": "____"},
            ],
        )

    def test_extract_classic_sticker_rows_skips_entirely_empty_rows(self):
        frame = pd.DataFrame(
            {
                "Employee Code": [None, 174826],
                "NAME": ["", "Abdul Khader"],
                "LOCATION": [None, "Chennai"],
            }
        )

        rows = extract_classic_sticker_rows(
            frame,
            [
                {"column": "Employee Code", "label": "Employee Code"},
                {"column": "NAME", "label": "NAME"},
                {"column": "LOCATION", "label": "LOCATION"},
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["lines"],
            [
                {"label": "Employee Code", "value": "174826"},
                {"label": "NAME", "value": "Abdul Khader"},
                {"label": "LOCATION", "value": "Chennai"},
            ],
        )

    def test_extract_classic_sticker_rows_raises_for_unmatched_fields(self):
        frame = pd.DataFrame({"Employee Code": [174826], "NAME": ["Abdul Khader"]})

        with self.assertRaises(ValueError):
            extract_classic_sticker_rows(frame, [{"key": "SIZE", "label": "SIZE"}])

    def test_extract_classic_sticker_rows_uses_first_row_as_headers_for_unnamed_columns(self):
        frame = pd.DataFrame(
            {
                "Unnamed: 0": ["Sr. No.", 1],
                "Unnamed: 1": ["Employee Code ", 174826],
                "Unnamed: 2": ["NAME ", "Abdul Khader"],
                "Unnamed: 3": ["SIZE", "XL - 42"],
            }
        )

        rows = extract_classic_sticker_rows(
            frame,
            [
                {"column": "Employee Code", "label": "Employee Code"},
                {"column": "NAME", "label": "NAME"},
                {"column": "SIZE", "label": "SIZE"},
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["lines"],
            [
                {"label": "Employee Code", "value": "174826"},
                {"label": "NAME", "value": "Abdul Khader"},
                {"label": "SIZE", "value": "XL - 42"},
            ],
        )

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

    def test_generate_classic_stickers_pdf_uses_different_page_dimensions_for_sizes(self):
        sticker_rows = [{"lines": [{"label": "NAME", "value": "Abdul Khader"}]}]

        pdf_2x2 = generate_classic_stickers_pdf(sticker_rows, label_size="2x2", padding_in=0.1)
        pdf_4x6 = generate_classic_stickers_pdf(sticker_rows, label_size="4x6", padding_in=0.1)

        self.assertTrue(any(box == (144.0, 144.0) for box in _extract_media_boxes(pdf_2x2)))
        self.assertTrue(any(box == (288.0, 432.0) for box in _extract_media_boxes(pdf_4x6)))

    def test_suggest_classic_sticker_filename(self):
        self.assertEqual(
            suggest_classic_sticker_filename("orders march.xlsx", "4x6"),
            "orders-march-classic-stickers-4x6.pdf",
        )

    def test_suggest_classic_sticker_filename_without_base_name(self):
        self.assertEqual(
            suggest_classic_sticker_filename("", "4x6"),
            "classic-stickers-4x6.pdf",
        )

    @unittest.skipIf(TestClient is None, "fastapi test client requires httpx")
    def test_api_upload_generates_classic_sticker_pdf(self):
        csv_bytes = (
            b"Employee Code,NAME,SIZE,LOCATION\n"
            b"174826,Abdul Khader,XL - 42,Chennai\n"
        )
        response = self.client.post(
            "/api/automate/upload",
            files={"file": ("stickers.csv", csv_bytes, "text/csv")},
            data={
                "mode": "classic_stickers_pdf",
                "classic_sticker_config": """
                {
                  "sheet_name": "data",
                  "label_size": "4x2",
                  "padding_in": 0.1,
                  "fields": [
                    {"column": "Employee Code", "label": "Employee Code"},
                    {"column": "NAME", "label": "NAME"},
                    {"column": "SIZE", "label": "SIZE"}
                  ]
                }
                """,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn("classic-stickers-4x2.pdf", response.headers["content-disposition"])
        self.assertGreater(len(response.content), 0)

    @unittest.skipIf(TestClient is None, "fastapi test client requires httpx")
    def test_api_upload_rejects_missing_sheet(self):
        csv_bytes = b"Employee Code,NAME\n174826,Abdul Khader\n"
        response = self.client.post(
            "/api/automate/upload",
            files={"file": ("stickers.csv", csv_bytes, "text/csv")},
            data={
                "mode": "classic_stickers_pdf",
                "classic_sticker_config": """
                {
                  "sheet_name": "MissingSheet",
                  "label_size": "4x2",
                  "padding_in": 0.1,
                  "fields": [{"column": "Employee Code", "label": "Employee Code"}]
                }
                """,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("was not found", response.json()["detail"])

    @unittest.skipIf(TestClient is None, "fastapi test client requires httpx")
    def test_api_upload_rejects_empty_fields_config(self):
        csv_bytes = b"Employee Code,NAME\n174826,Abdul Khader\n"
        response = self.client.post(
            "/api/automate/upload",
            files={"file": ("stickers.csv", csv_bytes, "text/csv")},
            data={
                "mode": "classic_stickers_pdf",
                "classic_sticker_config": """
                {
                  "sheet_name": "data",
                  "label_size": "4x2",
                  "padding_in": 0.1,
                  "fields": []
                }
                """,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Select at least one field", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
