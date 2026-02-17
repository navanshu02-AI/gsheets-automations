import unittest

import pandas as pd

from app.automations import build_delivery_print_sheet, run_automation_on_sheets


class DeliveryPrintTests(unittest.TestCase):
    def test_build_delivery_print_sheet_prefers_packed_qty(self):
        sheet = pd.DataFrame(
            {
                "Article Code": ["A1", "A2"],
                "Size": ["M", "L"],
                "EAN": ["111", "222"],
                "Order Qty": [5, 4],
                "Packed Qty": [3, ""],
                "Carton Count": [1, 2],
            }
        )
        sheet.attrs["sheet_metadata"] = {"po_number": "3100743891", "invoice_number": "INV-1"}

        delivery = build_delivery_print_sheet(sheet)

        assert delivery is not None
        self.assertEqual(
            list(delivery.columns),
            ["po_number", "invoice_number", "carton_count", "ean_code", "article_code", "size", "qty"],
        )
        self.assertEqual(delivery["qty"].tolist(), [3, 4])
        self.assertEqual(delivery["po_number"].tolist(), ["3100743891", "3100743891"])
        self.assertEqual(delivery["invoice_number"].tolist(), ["INV-1", "INV-1"])

    def test_build_delivery_print_sheet_uses_carton_1_when_missing(self):
        sheet = pd.DataFrame(
            {
                "Article Code": ["A1"],
                "Size": ["M"],
                "Order Qty": [2],
            }
        )

        delivery = build_delivery_print_sheet(sheet)

        assert delivery is not None
        self.assertEqual(delivery["carton_count"].tolist(), ["1"])
        self.assertEqual(delivery["qty"].tolist(), [2])

    def test_build_delivery_print_sheet_filters_invalid_rows(self):
        sheet = pd.DataFrame(
            {
                "Article Code": ["A1", "", "A3"],
                "Size": ["M", "L", ""],
                "Packed Qty": [0, 4, 1],
            }
        )

        delivery = build_delivery_print_sheet(sheet)

        assert delivery is not None
        self.assertEqual(len(delivery), 0)

    def test_run_automation_on_sheets_adds_delivery_print_sheet(self):
        sheets = {
            "Sheet1": pd.DataFrame(
                {
                    "Article Code": ["A1"],
                    "Size": ["M"],
                    "EAN": ["123456"],
                    "Packed Qty": [2],
                    "Carton Count": [1],
                }
            )
        }

        output = run_automation_on_sheets(sheets)

        self.assertIn("Sheet1__delivery_print", output)
        self.assertEqual(
            output["Sheet1__delivery_print"]["article_code"].tolist(),
            ["A1"],
        )


if __name__ == "__main__":
    unittest.main()
