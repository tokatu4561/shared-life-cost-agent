from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
from typing import Literal

import boto3
from googleapiclient.errors import HttpError

from .config import MissingConfigurationError, SheetsError, aws_region
from .google_secret import SHEETS_SCOPES, get_google_secret, service_account_credentials, spreadsheet_id
from .sheets_tool import _build_sheets_service

JST = timezone(timedelta(hours=9))
ExpenseQueryIntent = Literal["self_total", "overall_total", "by_user_total", "unsupported"]

ALLOWED_INTENTS: set[str] = {"self_total", "overall_total", "by_user_total", "unsupported"}
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
HAIKU_45_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"


@dataclass(frozen=True)
class ExpenseQueryRequest:
    line_user_id: str
    line_display_name: str
    line_message_id: str
    text: str


@dataclass(frozen=True)
class ExpenseRow:
    line_display_name: str
    line_user_id: str
    total: int


def process_expense_query(payload: dict) -> dict:
    try:
        request = _parse_request(payload)
    except Exception as error:
        return _failed("configuration_error", f"入力形式が不正です: {error}")

    try:
        try:
            intent = classify_expense_query(request.text)
        except Exception as error:
            return _failed("classification_error", f"質問分類に失敗しました: {error}")

        if intent == "unsupported":
            return {
                "success": False,
                "status": "unsupported",
                "reason": "unsupported_query",
                "replyMessage": "今月の自分の合計、全体合計、ユーザー別合計に答えられます。",
            }

        rows = fetch_current_month_expenses()
        reply_message = build_expense_query_reply(intent, rows, request, datetime.now(JST))
        return {
            "success": True,
            "status": "answered",
            "replyMessage": reply_message,
        }
    except MissingConfigurationError as error:
        return _failed("configuration_error", str(error))
    except SheetsError as error:
        return _failed("sheets_error", str(error))
    except Exception as error:
        return _failed("failed", f"集計処理に失敗しました: {error}")


def classify_expense_query(text: str) -> ExpenseQueryIntent:
    region = aws_region()
    bedrock_runtime = boto3.client(
        "bedrock-runtime",
        region_name=region,
        endpoint_url=f"https://bedrock-runtime.{region}.amazonaws.com",
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 128,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": _build_classification_prompt(text)}],
            }
        ],
    }

    response = bedrock_runtime.invoke_model(
        modelId=_resolve_model_id(),
        body=json.dumps(body).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
    )
    response_body = json.loads(response["body"].read())
    parsed = _parse_json(response_body["content"][0]["text"])
    intent = str(parsed.get("intent") or "").strip()
    if intent not in ALLOWED_INTENTS:
        return "unsupported"
    return intent  # type: ignore[return-value]


def fetch_current_month_expenses(now: datetime | None = None) -> list[ExpenseRow]:
    google_secret = get_google_secret()
    target_spreadsheet_id = spreadsheet_id(google_secret)
    service = _build_sheets_service(google_secret)
    sheet_name = _current_month_sheet_name(now or datetime.now(JST))

    try:
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=target_spreadsheet_id,
                range=f"'{sheet_name}'!A:I",
            )
            .execute()
        )
    except HttpError as error:
        if error.resp.status == 400:
            return []
        raise SheetsError(f"Google Sheetsから集計データを取得できませんでした: {error}") from error
    except Exception as error:
        raise SheetsError(f"Google Sheetsから集計データを取得できませんでした: {error}") from error

    return parse_expense_rows(result.get("values", []))


def parse_expense_rows(values: list[list[object]]) -> list[ExpenseRow]:
    rows: list[ExpenseRow] = []
    for row in values[1:]:
        line_user_id = _cell(row, 3)
        total = _parse_total(_cell(row, 6))
        if not line_user_id or total is None:
            continue

        rows.append(
            ExpenseRow(
                line_display_name=_cell(row, 2),
                line_user_id=line_user_id,
                total=total,
            )
        )
    return rows


def build_expense_query_reply(
    intent: ExpenseQueryIntent,
    rows: list[ExpenseRow],
    request: ExpenseQueryRequest,
    now: datetime,
) -> str:
    month = _current_month_sheet_name(now)
    if not rows:
        return f"{month} の登録はまだありません。"

    if intent == "self_total":
        total = sum(row.total for row in rows if row.line_user_id == request.line_user_id)
        name = request.line_display_name or "あなた"
        return f"{month} の{name}さんの合計は {total:,}円です。"

    if intent == "overall_total":
        total = sum(row.total for row in rows)
        return f"{month} の全体合計は {total:,}円です。"

    if intent == "by_user_total":
        totals: dict[str, int] = {}
        names: dict[str, str] = {}
        for row in rows:
            totals[row.line_user_id] = totals.get(row.line_user_id, 0) + row.total
            if row.line_display_name:
                names[row.line_user_id] = row.line_display_name

        lines = [f"{month} のユーザー別合計です。"]
        for line_user_id, total in sorted(totals.items(), key=lambda item: (-item[1], _display_name(item[0], names))):
            lines.append(f"{_display_name(line_user_id, names)}: {total:,}円")
        return "\n".join(lines)

    return "今月の自分の合計、全体合計、ユーザー別合計に答えられます。"


def _parse_request(payload: dict) -> ExpenseQueryRequest:
    return ExpenseQueryRequest(
        line_user_id=str(payload["lineUserId"]),
        line_display_name=str(payload.get("lineDisplayName") or ""),
        line_message_id=str(payload["lineMessageId"]),
        text=str(payload["text"]),
    )


def _build_classification_prompt(text: str) -> str:
    return (
        "あなたはLINE家計精算Agentの質問分類器です。\n"
        "ユーザーの質問を次のintentのどれか1つに分類し、JSONだけを返してください。\n"
        "- self_total: 今月の質問者本人の合計金額を尋ねている\n"
        "- overall_total: 今月の全体合計金額を尋ねている\n"
        "- by_user_total: 今月のユーザー別・人別の合計金額を尋ねている\n"
        "- unsupported: 上記以外、月指定、店舗別、カテゴリ別、修正依頼など\n"
        "形式: {\"intent\":\"self_total|overall_total|by_user_total|unsupported\"}\n\n"
        f"質問:\n{text}"
    )


def _resolve_model_id() -> str:
    configured_model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID).strip()
    if configured_model_id == HAIKU_45_MODEL_ID:
        return DEFAULT_MODEL_ID
    return configured_model_id


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _current_month_sheet_name(now: datetime) -> str:
    return now.astimezone(JST).strftime("%Y-%m")


def _cell(row: list[object], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip().removeprefix("'")


def _parse_total(value: str) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    return int(digits)


def _display_name(line_user_id: str, names: dict[str, str]) -> str:
    return names.get(line_user_id) or _short_user_id(line_user_id)


def _short_user_id(line_user_id: str) -> str:
    if len(line_user_id) <= 8:
        return line_user_id
    return f"{line_user_id[:4]}...{line_user_id[-4:]}"


def _failed(reason: str, detail: str) -> dict:
    return {
        "success": False,
        "status": "failed",
        "reason": reason,
        "replyMessage": "集計に失敗しました。\n時間をおいてもう一度試してください。",
        "errorDetail": detail,
    }
