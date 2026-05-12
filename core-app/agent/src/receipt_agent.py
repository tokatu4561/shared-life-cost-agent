from __future__ import annotations

from datetime import datetime, timezone, timedelta
import traceback

from .config import MissingConfigurationError, SheetsError
from .normalizer import normalize_receipt
from .sheets_tool import append_receipt
from .types import NormalizedReceipt, ReceiptRequest
from .vision_ocr_tool import extract_text

JST = timezone(timedelta(hours=9))


def process_receipt(payload: dict) -> dict:
    try:
        request = _parse_request(payload)
    except Exception as error:
        return _failed("configuration_error", f"入力形式が不正です: {error}")

    try:
        ocr_text = extract_text(request.bucket, request.key)
        receipt = normalize_receipt(
            ocr_text,
            request.image_url,
            request.line_user_id,
            request.line_display_name,
            request.line_message_id,
        )

        if not receipt.has_required_fields():
            return {
                "success": False,
                "status": "skipped",
                "reason": "missing_required_fields",
                "replyMessage": (
                    "レシートを読み取れませんでした。\n"
                    "店舗名または合計金額を確認できません。レシート全体が写るように撮影して、もう一度送ってください。"
                ),
                "receipt": _receipt_to_response(receipt),
            }

        sheet_result = append_receipt(receipt, registered_at=datetime.now(JST))
        registered = sheet_result.get("alreadyRegistered") is not True
        return {
            "success": True,
            "status": "registered",
            "replyMessage": _success_message(receipt, already_registered=not registered),
            "receipt": _receipt_to_response(receipt),
            "sheet": sheet_result,
        }
    except MissingConfigurationError as error:
        return _failed("configuration_error", str(error))
    except SheetsError as error:
        return _failed("sheets_error", str(error))
    except Exception as error:
        traceback.print_exc()
        return _failed("failed", f"レシート処理に失敗しました: {error}")


def _parse_request(payload: dict) -> ReceiptRequest:
    return ReceiptRequest(
        line_user_id=str(payload["lineUserId"]),
        line_display_name=str(payload.get("lineDisplayName") or ""),
        line_message_id=str(payload["lineMessageId"]),
        bucket=str(payload["bucket"]),
        key=str(payload["key"]),
        image_url=str(payload.get("imageUrl") or payload["imageS3Uri"]),
    )


def _success_message(receipt: NormalizedReceipt, already_registered: bool = False) -> str:
    lines = [
        "登録済みです。" if already_registered else "登録しました。",
        f"店舗：{receipt.store}",
        f"カテゴリ：{receipt.category}",
        f"合計：{receipt.total:,}円",
    ]
    if receipt.receipt_date:
        lines.insert(1, f"日付：{receipt.receipt_date}")
    return "\n".join(lines)


def _receipt_to_response(receipt: NormalizedReceipt) -> dict:
    return {
        "lineUserId": receipt.line_user_id,
        "lineDisplayName": receipt.line_display_name,
        "lineMessageId": receipt.line_message_id,
        "receiptDate": receipt.receipt_date,
        "store": receipt.store,
        "category": receipt.category,
        "total": receipt.total,
        "imageUrl": receipt.image_url,
    }


def _failed(reason: str, detail: str) -> dict:
    return {
        "success": False,
        "status": "failed",
        "reason": reason,
        "replyMessage": "レシート処理に失敗しました。\n時間をおいてもう一度送ってください。",
        "errorDetail": detail,
    }
