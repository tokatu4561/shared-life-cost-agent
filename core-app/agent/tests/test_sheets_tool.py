from __future__ import annotations

from datetime import datetime, timezone
import types
import unittest
from unittest.mock import MagicMock, patch

fake_googleapiclient = types.ModuleType("googleapiclient")
fake_googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
fake_googleapiclient_discovery.build = MagicMock()

fake_google = types.ModuleType("google")
fake_google_oauth2 = types.ModuleType("google.oauth2")
fake_google_service_account = types.ModuleType("google.oauth2.service_account")
fake_google_service_account.Credentials = MagicMock()

with patch.dict(
    "sys.modules",
    {
        "boto3": MagicMock(),
        "google": fake_google,
        "google.oauth2": fake_google_oauth2,
        "google.oauth2.service_account": fake_google_service_account,
        "googleapiclient": fake_googleapiclient,
        "googleapiclient.discovery": fake_googleapiclient_discovery,
    },
):
    from src import sheets_tool
    from src.types import NormalizedReceipt


class SheetsToolTest(unittest.TestCase):
    def test_appends_receipt_date_as_user_entered_value(self) -> None:
        service = _fake_sheets_service()
        receipt = NormalizedReceipt(
            line_user_id="U001",
            line_display_name="太郎",
            line_message_id="m001",
            receipt_date="2025-05-24",
            store="ローソン",
            category="食費",
            total=1200,
            image_url="https://example.com/receipt.jpg",
        )

        with (
            patch.object(sheets_tool, "get_google_secret", return_value={}),
            patch.object(sheets_tool, "spreadsheet_id", return_value="spreadsheet-id"),
            patch.object(sheets_tool, "_build_sheets_service", return_value=service),
        ):
            sheets_tool.append_receipt(receipt, datetime(2025, 5, 24, 12, 0, tzinfo=timezone.utc))

        append_call = service.spreadsheets.return_value.values.return_value.append.call_args.kwargs
        self.assertEqual(append_call["valueInputOption"], "USER_ENTERED")
        self.assertEqual(append_call["body"]["values"][0][1], "2025-05-24")

    def test_uses_current_month_sheet_when_receipt_date_month_is_different(self) -> None:
        service = _fake_sheets_service()
        receipt = _receipt(receipt_date="2025-05-24")

        with (
            patch.object(sheets_tool, "get_google_secret", return_value={}),
            patch.object(sheets_tool, "spreadsheet_id", return_value="spreadsheet-id"),
            patch.object(sheets_tool, "_build_sheets_service", return_value=service),
        ):
            result = sheets_tool.append_receipt(receipt, datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc))

        append_call = service.spreadsheets.return_value.values.return_value.append.call_args.kwargs
        self.assertEqual(append_call["range"], "'2025-06'!A:I")
        self.assertEqual(append_call["body"]["values"][0][1], "2025-05-24")
        self.assertTrue(result["receiptDateMonthMismatched"])

    def test_uses_receipt_month_sheet_when_receipt_date_month_is_current(self) -> None:
        service = _fake_sheets_service()
        receipt = _receipt(receipt_date="2025-05-24")

        with (
            patch.object(sheets_tool, "get_google_secret", return_value={}),
            patch.object(sheets_tool, "spreadsheet_id", return_value="spreadsheet-id"),
            patch.object(sheets_tool, "_build_sheets_service", return_value=service),
        ):
            result = sheets_tool.append_receipt(receipt, datetime(2025, 5, 24, 12, 0, tzinfo=timezone.utc))

        append_call = service.spreadsheets.return_value.values.return_value.append.call_args.kwargs
        self.assertEqual(append_call["range"], "'2025-05'!A:I")
        self.assertFalse(result["receiptDateMonthMismatched"])

    def test_uses_current_month_sheet_when_receipt_date_is_none(self) -> None:
        service = _fake_sheets_service()
        receipt = _receipt(receipt_date=None)

        with (
            patch.object(sheets_tool, "get_google_secret", return_value={}),
            patch.object(sheets_tool, "spreadsheet_id", return_value="spreadsheet-id"),
            patch.object(sheets_tool, "_build_sheets_service", return_value=service),
        ):
            result = sheets_tool.append_receipt(receipt, datetime(2025, 5, 24, 12, 0, tzinfo=timezone.utc))

        append_call = service.spreadsheets.return_value.values.return_value.append.call_args.kwargs
        self.assertEqual(append_call["range"], "'2025-05'!A:I")
        self.assertEqual(append_call["body"]["values"][0][1], "")
        self.assertFalse(result["receiptDateMonthMismatched"])


def _receipt(receipt_date: str | None) -> NormalizedReceipt:
    return NormalizedReceipt(
        line_user_id="U001",
        line_display_name="太郎",
        line_message_id="m001",
        receipt_date=receipt_date,
        store="ローソン",
        category="食費",
        total=1200,
        image_url="https://example.com/receipt.jpg",
    )


def _fake_sheets_service() -> MagicMock:
    service = MagicMock()
    spreadsheets = service.spreadsheets.return_value
    values = spreadsheets.values.return_value
    spreadsheets.get.return_value.execute.return_value = {"sheets": []}
    spreadsheets.batchUpdate.return_value.execute.return_value = {}
    values.get.return_value.execute.return_value = {"values": []}
    values.update.return_value.execute.return_value = {}
    values.append.return_value.execute.return_value = {
        "updates": {
            "updatedRange": "'2025-05'!A2:I2",
        }
    }
    return service


if __name__ == "__main__":
    unittest.main()
