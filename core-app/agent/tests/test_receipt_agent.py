from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

fake_google = types.ModuleType("google")
fake_google_cloud = types.ModuleType("google.cloud")
fake_google_cloud_vision = types.ModuleType("google.cloud.vision")
fake_google_cloud_vision.ImageAnnotatorClient = MagicMock()
fake_google_cloud_vision.Image = MagicMock()
fake_googleapiclient = types.ModuleType("googleapiclient")
fake_googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
fake_googleapiclient_discovery.build = MagicMock()
fake_google_oauth2 = types.ModuleType("google.oauth2")
fake_google_service_account = types.ModuleType("google.oauth2.service_account")
fake_google_service_account.Credentials = MagicMock()

with patch.dict(
    "sys.modules",
    {
        "boto3": MagicMock(),
        "google": fake_google,
        "google.cloud": fake_google_cloud,
        "google.cloud.vision": fake_google_cloud_vision,
        "google.oauth2": fake_google_oauth2,
        "google.oauth2.service_account": fake_google_service_account,
        "googleapiclient": fake_googleapiclient,
        "googleapiclient.discovery": fake_googleapiclient_discovery,
    },
):
    from src import receipt_agent
    from src.types import NormalizedReceipt


class ReceiptAgentTest(unittest.TestCase):
    def test_success_message_includes_warning_when_receipt_date_month_is_mismatched(self) -> None:
        result = _process_receipt_result(receipt_date_month_mismatched=True)

        self.assertTrue(result["success"])
        self.assertIn("読み取った日付が今月ではありません。", result["replyMessage"])
        self.assertIn("今月分として登録しました", result["replyMessage"])

    def test_success_message_does_not_include_warning_when_receipt_date_month_is_not_mismatched(self) -> None:
        result = _process_receipt_result(receipt_date_month_mismatched=False)

        self.assertTrue(result["success"])
        self.assertNotIn("今月のレシートではない可能性があります", result["replyMessage"])


def _process_receipt_result(receipt_date_month_mismatched: bool) -> dict:
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
    payload = {
        "lineUserId": "U001",
        "lineDisplayName": "太郎",
        "lineMessageId": "m001",
        "bucket": "receipt-bucket",
        "key": "receipts/U001/m001.jpg",
        "imageUrl": "https://example.com/receipt.jpg",
    }

    with (
        patch.object(receipt_agent, "extract_text", return_value="ocr text"),
        patch.object(receipt_agent, "normalize_receipt", return_value=receipt),
        patch.object(
            receipt_agent,
            "append_receipt",
            return_value={
                "sheetName": "2025-06",
                "updatedRange": "'2025-06'!A2:I2",
                "alreadyRegistered": False,
                "receiptDateMonthMismatched": receipt_date_month_mismatched,
            },
        ),
    ):
        return receipt_agent.process_receipt(payload)


if __name__ == "__main__":
    unittest.main()
