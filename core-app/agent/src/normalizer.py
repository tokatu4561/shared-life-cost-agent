from __future__ import annotations

import json
import os
import re

import boto3

from .config import aws_region
from .types import NormalizedReceipt, ReceiptCategory

ALLOWED_CATEGORIES: set[str] = {"食費", "日用品", "その他"}
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
HAIKU_45_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"


def normalize_receipt(ocr_text: str, image_s3_uri: str, line_message_id: str) -> NormalizedReceipt:
    region = aws_region()
    bedrock_runtime = boto3.client(
        "bedrock-runtime",
        region_name=region,
        endpoint_url=f"https://bedrock-runtime.{region}.amazonaws.com",
    )
    prompt = _build_prompt(ocr_text)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
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
    text = response_body["content"][0]["text"]
    parsed = _parse_json(text)

    category = parsed.get("category")
    if category not in ALLOWED_CATEGORIES:
        category = "その他"

    return NormalizedReceipt(
        line_message_id=line_message_id,
        receipt_date=_nullable_string(parsed.get("receiptDate")),
        store=_nullable_string(parsed.get("store")),
        category=category,  # type: ignore[arg-type]
        total=_nullable_int(parsed.get("total")),
        image_s3_uri=image_s3_uri,
    )


def _resolve_model_id() -> str:
    configured_model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID).strip()
    if configured_model_id == HAIKU_45_MODEL_ID:
        return DEFAULT_MODEL_ID
    return configured_model_id


def _build_prompt(ocr_text: str) -> str:
    return (
        "あなたは同棲生活の月末精算用レシート記録エージェントです。\n"
        "Google Cloud Vision APIで抽出した日本のレシートOCRテキストから、Google Sheets登録用JSONだけを返してください。\n"
        "カテゴリは必ず「食費」「日用品」「その他」のどれかです。\n"
        "日付が不明な場合は null にしてください。今日の日付で補完してはいけません。\n"
        "店舗名または合計金額が不明な場合も推測しすぎず null にしてください。\n"
        "合計金額は税込合計・総合計・お買上計など、精算に使う最終支払金額を優先してください。\n"
        "返答は説明なしのJSONのみです。\n"
        "形式: {\"receiptDate\":\"YYYY-MM-DD|null\",\"store\":\"string|null\",\"category\":\"食費|日用品|その他\",\"total\":1234|null}\n\n"
        f"OCRテキスト:\n{ocr_text}"
    )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _nullable_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null" or text == "不明":
        return None
    return text


def _nullable_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = re.sub(r"[^0-9]", "", str(value))
    if not digits:
        return None
    return int(digits)
