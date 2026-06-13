from __future__ import annotations

from datetime import datetime

from googleapiclient.discovery import build

from .config import SheetsError
from .google_secret import SHEETS_SCOPES, get_google_secret, service_account_credentials, spreadsheet_id
from .types import NormalizedReceipt

HEADERS = [
    "登録日時",
    "レシート日付",
    "LINE表示名",
    "LINEユーザーID",
    "店舗名",
    "カテゴリ",
    "合計金額",
    "画像URL",
    "LINEメッセージID",
]
LINE_MESSAGE_ID_COLUMN = "I"
FORMULA_PREFIXES = ("=", "+", "-", "@")


def append_receipt(receipt: NormalizedReceipt, registered_at: datetime) -> dict:
    google_secret = get_google_secret()
    target_spreadsheet_id = spreadsheet_id(google_secret)

    service = _build_sheets_service(google_secret)
    sheet_name = _resolve_sheet_name(receipt.receipt_date, registered_at)
    receipt_date_month_mismatched = _receipt_date_month_mismatched(receipt.receipt_date, registered_at)

    try:
        existing_receipt = _find_existing_receipt(service, target_spreadsheet_id, receipt.line_message_id)
        if existing_receipt:
            return {
                "sheetName": existing_receipt["sheetName"],
                "updatedRange": existing_receipt["updatedRange"],
                "alreadyRegistered": True,
                "receiptDateMonthMismatched": False,
            }

        _ensure_monthly_sheet(service, target_spreadsheet_id, sheet_name)
        row = [
            _safe_sheet_text(registered_at.isoformat()),
            _safe_sheet_text(receipt.receipt_date or ""),
            _safe_sheet_text(receipt.line_display_name),
            _safe_sheet_text(receipt.line_user_id),
            _safe_sheet_text(receipt.store or ""),
            _safe_sheet_text(receipt.category),
            receipt.total,
            _safe_sheet_text(receipt.image_url),
            _safe_sheet_text(receipt.line_message_id),
        ]
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=target_spreadsheet_id,
                range=f"'{sheet_name}'!A:{LINE_MESSAGE_ID_COLUMN}",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
            .execute()
        )
    except Exception as error:
        raise SheetsError(f"Google Sheetsへの転記に失敗しました: {error}") from error

    return {
        "sheetName": sheet_name,
        "updatedRange": result.get("updates", {}).get("updatedRange", ""),
        "alreadyRegistered": False,
        "receiptDateMonthMismatched": receipt_date_month_mismatched,
    }


def _build_sheets_service(google_secret: dict):
    credentials = service_account_credentials(google_secret, SHEETS_SCOPES)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _resolve_sheet_name(receipt_date: str | None, registered_at: datetime) -> str:
    if receipt_date and not _receipt_date_month_mismatched(receipt_date, registered_at):
        return receipt_date[:7]
    return registered_at.strftime("%Y-%m")


def _receipt_date_month_mismatched(receipt_date: str | None, registered_at: datetime) -> bool:
    if not receipt_date:
        return False
    return receipt_date[:7] != registered_at.strftime("%Y-%m")


def _safe_sheet_text(value: str) -> str:
    if value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _ensure_monthly_sheet(service, spreadsheet_id: str, sheet_name: str) -> None:
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = spreadsheet.get("sheets", [])
    if any(sheet.get("properties", {}).get("title") == sheet_name for sheet in sheets):
        _ensure_header(service, spreadsheet_id, sheet_name)
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": sheet_name,
                            "gridProperties": {
                                "rowCount": 1000,
                                "columnCount": len(HEADERS),
                            },
                        }
                    }
                }
            ]
        },
    ).execute()
    _ensure_header(service, spreadsheet_id, sheet_name)


def _ensure_header(service, spreadsheet_id: str, sheet_name: str) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A1:{LINE_MESSAGE_ID_COLUMN}1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()


def _find_existing_receipt(service, spreadsheet_id: str, line_message_id: str) -> dict | None:
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in spreadsheet.get("sheets", []):
        sheet_name = sheet.get("properties", {}).get("title")
        if not sheet_name:
            continue

        existing_receipt = _find_existing_receipt_in_column(
            service,
            spreadsheet_id,
            sheet_name,
            LINE_MESSAGE_ID_COLUMN,
            line_message_id,
        )
        if existing_receipt:
            return existing_receipt

    return None


def _find_existing_receipt_in_column(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    column: str,
    line_message_id: str,
) -> dict | None:
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!{column}:{column}",
        )
        .execute()
    )
    values = result.get("values", [])
    for index, row in enumerate(values, start=1):
        if row and str(row[0]).strip() == line_message_id:
            return {
                "sheetName": sheet_name,
                "updatedRange": f"'{sheet_name}'!A{index}:{LINE_MESSAGE_ID_COLUMN}{index}",
            }
    return None
