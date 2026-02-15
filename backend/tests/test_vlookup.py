import unittest

import pandas as pd

from app.automations import TransformConfig, apply_transform_pipeline


class VLookupExcelSemanticsTests(unittest.TestCase):
    def test_returns_value_from_column_to_right(self):
        sheets = {
            "orders": pd.DataFrame(
                {
                    "sku": ["A", "B"],
                    "qty": [2, 3],
                }
            ),
            "catalog": pd.DataFrame(
                {
                    "sku": ["A", "B"],
                    "name": ["Alpha", "Beta"],
                    "price": [10, 20],
                }
            ),
        }

        config = TransformConfig.model_validate(
            {
                "base_sheet": "orders",
                "vlookup_operations": [
                    {
                        "lookup_value_column": "sku",
                        "table_array_sheet": "catalog",
                        "table_array_lookup_column": "sku",
                        "col_index_num": 2,
                        "range_lookup": False,
                        "output_column": "product_name",
                    }
                ],
            }
        )

        output_sheets, result_sheets = apply_transform_pipeline(sheets, config)
        result_df = output_sheets[result_sheets[0]]
        self.assertEqual(result_df["product_name"].tolist(), ["Alpha", "Beta"])

    def test_error_when_col_index_attempts_left_column(self):
        # lookup column is not first in the source sheet; table_array starts at `lookup_key`
        # so asking for col_index_num=0 (left of first table_array column) must fail.
        sheets = {
            "orders": pd.DataFrame({"lookup_key": ["x"]}),
            "lookup": pd.DataFrame(
                {
                    "left_col": ["L"],
                    "lookup_key": ["x"],
                    "right_col": ["R"],
                }
            ),
        }

        config = TransformConfig.model_validate(
            {
                "base_sheet": "orders",
                "vlookup_operations": [
                    {
                        "lookup_value_column": "lookup_key",
                        "table_array_sheet": "lookup",
                        "table_array_lookup_column": "lookup_key",
                        "col_index_num": 0,
                        "range_lookup": False,
                        "output_column": "out",
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "col_index_num must be >= 1"):
            apply_transform_pipeline(sheets, config)

    def test_error_when_col_index_out_of_bounds(self):
        sheets = {
            "orders": pd.DataFrame({"sku": ["A"]}),
            "catalog": pd.DataFrame({"sku": ["A"], "name": ["Alpha"]}),
        }

        config = TransformConfig.model_validate(
            {
                "base_sheet": "orders",
                "vlookup_operations": [
                    {
                        "lookup_value_column": "sku",
                        "table_array_sheet": "catalog",
                        "table_array_lookup_column": "sku",
                        "col_index_num": 3,
                        "range_lookup": False,
                        "output_column": "out",
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "out of bounds"):
            apply_transform_pipeline(sheets, config)

    def test_exact_match_returns_na_when_not_found(self):
        sheets = {
            "orders": pd.DataFrame({"sku": ["A", "MISSING"]}),
            "catalog": pd.DataFrame({"sku": ["A"], "name": ["Alpha"]}),
        }

        config = TransformConfig.model_validate(
            {
                "base_sheet": "orders",
                "vlookup_operations": [
                    {
                        "lookup_value_column": "sku",
                        "table_array_sheet": "catalog",
                        "table_array_lookup_column": "sku",
                        "col_index_num": 2,
                        "range_lookup": False,
                        "output_column": "name_out",
                    }
                ],
            }
        )

        output_sheets, result_sheets = apply_transform_pipeline(sheets, config)
        result_df = output_sheets[result_sheets[0]]
        self.assertEqual(result_df["name_out"].tolist(), ["Alpha", "#N/A"])

    def test_omitted_range_lookup_uses_approximate(self):
        sheets = {
            "orders": pd.DataFrame({"inv_amt": [5, 15, 25]}),
            "bands": pd.DataFrame(
                {
                    "threshold": [0, 10, 20],
                    "band": ["LOW", "MEDIUM", "HIGH"],
                }
            ),
        }

        config = TransformConfig.model_validate(
            {
                "base_sheet": "orders",
                "vlookup_operations": [
                    {
                        "lookup_value_column": "inv_amt",
                        "table_array_sheet": "bands",
                        "table_array_lookup_column": "threshold",
                        "col_index_num": 2,
                        "output_column": "band_out",
                    }
                ],
            }
        )

        output_sheets, result_sheets = apply_transform_pipeline(sheets, config)
        result_df = output_sheets[result_sheets[0]]
        self.assertEqual(result_df["band_out"].tolist(), ["LOW", "MEDIUM", "HIGH"])


if __name__ == "__main__":
    unittest.main()
