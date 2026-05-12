from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

with patch.dict("sys.modules", {"boto3": MagicMock()}):
    from src.normalizer import _normalize_receipt_date


class NormalizeReceiptDateTest(unittest.TestCase):
    def test_removes_leading_single_quote(self) -> None:
        self.assertEqual(_normalize_receipt_date("'2026-05-10"), "2026-05-10")

    def test_accepts_iso_date(self) -> None:
        self.assertEqual(_normalize_receipt_date("2026-05-10"), "2026-05-10")

    def test_nullish_values_return_none(self) -> None:
        for value in ("", "null", "不明", None):
            with self.subTest(value=value):
                self.assertIsNone(_normalize_receipt_date(value))

    def test_invalid_date_format_returns_none(self) -> None:
        for value in ("2026/05/10", "2026-5-10", "May 10, 2026"):
            with self.subTest(value=value):
                self.assertIsNone(_normalize_receipt_date(value))


if __name__ == "__main__":
    unittest.main()
