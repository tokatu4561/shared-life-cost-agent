from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import unicodedata

import boto3
from googleapiclient.errors import HttpError

from .config import MissingConfigurationError, SheetsError, aws_region
from .expense_query_prompts import build_query_plan_prompt
from .google_secret import SHEETS_SCOPES, get_google_secret, service_account_credentials, spreadsheet_id
from .sheets_tool import _build_sheets_service

JST = timezone(timedelta(hours=9))

ALLOWED_METRIC_TYPES: set[str] = {"sum"}
ALLOWED_VALUE_FROM: set[str] = {"lineUserId"}
NUMERIC_COLUMNS: set[str] = {"合計金額"}
STANDARD_HEADERS = ["登録日時", "レシート日付", "LINE表示名", "LINEユーザーID", "店舗名", "カテゴリ", "合計金額", "画像URL", "LINEメッセージID"]
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
HAIKU_45_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"
LINE_USER_ID_PATTERN = re.compile(r"\bU[0-9A-Za-z]{8,}\b")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpenseQueryRequest:
    line_user_id: str
    line_display_name: str
    line_message_id: str
    text: str


@dataclass(frozen=True)
class ExpenseTable:
    sheet_name: str
    headers: list[str]
    rows: list[dict[str, str]]

    def to_values(self) -> list[list[str]]:
        return [self.headers, *[[row.get(header, "") for header in self.headers] for row in self.rows]]


@dataclass(frozen=True)
class ExpenseQueryPlan:
    metric: dict[str, object]
    group_by: list[str]
    display_columns: list[str]
    filters: list[dict[str, object]]
    sort: list[dict[str, object]]


@dataclass(frozen=True)
class AggregationGroup:
    label: str
    value: int
    matched_labels: list[str]


@dataclass(frozen=True)
class AggregationResult:
    plan: ExpenseQueryPlan
    groups: list[AggregationGroup]


class UnsupportedExpenseQueryError(Exception):
    pass


def process_expense_query(payload: dict) -> dict:
    try:
        request = _parse_request(payload)
    except Exception as error:
        return _failed("configuration_error", f"入力形式が不正です: {error}")

    try:
        table = fetch_current_month_expense_table()
        try:
            plan = build_expense_query_plan(request.text, table, request)
        except UnsupportedExpenseQueryError as error:
            _log_expense_query_event("expense_query_unsupported", stage="plan_generation", reason=str(error))
            return {
                "success": False,
                "status": "unsupported",
                "reason": "unsupported_query",
                "replyMessage": _unsupported_reply(),
            }
        except Exception as error:
            return _failed("classification_error", f"集計プラン生成に失敗しました: {error}")

        try:
            result = execute_expense_query_plan(plan, table, request)
            _log_expense_query_event("expense_query_plan_executed", groupCount=len(result.groups), emptySheet=not table.rows)
        except UnsupportedExpenseQueryError as error:
            _log_expense_query_event("expense_query_unsupported", stage="plan_execution", reason=str(error), parsedPlan=plan)
            return {
                "success": False,
                "status": "unsupported",
                "reason": "unsupported_query",
                "replyMessage": _unsupported_reply(),
            }

        if not table.rows:
            return {
                "success": True,
                "status": "answered",
                "replyMessage": f"{table.sheet_name} の登録はまだありません。",
            }

        reply_message = build_aggregation_reply(result, request, datetime.now(JST))
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


def build_expense_query_plan(text: str, table: ExpenseTable, request: ExpenseQueryRequest | None = None) -> ExpenseQueryPlan:
    deterministic_plan = _build_deterministic_query_plan(text, table, request)
    if deterministic_plan is not None:
        _log_expense_query_event("expense_query_plan_fallback_used", parsedPlan=_query_plan_to_log_dict(deterministic_plan), fallbackType="deterministic")
        return deterministic_plan

    region = aws_region()
    bedrock_runtime = boto3.client(
        "bedrock-runtime",
        region_name=region,
        endpoint_url=f"https://bedrock-runtime.{region}.amazonaws.com",
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": build_query_plan_prompt(text, table.sheet_name, table.headers)}],
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
    raw_plan_text = str(response_body["content"][0]["text"])
    _log_expense_query_event("expense_query_plan_llm_response", rawPlanText=raw_plan_text)
    try:
        parsed = _parse_json(raw_plan_text)
        plan = _parse_query_plan(parsed)
        validate_expense_query_plan(plan, table)
        _log_expense_query_event("expense_query_plan_parsed", parsedPlan=_query_plan_to_log_dict(plan), fallbackUsed=False)
        return plan
    except UnsupportedExpenseQueryError as error:
        _log_expense_query_event("expense_query_plan_rejected", reason=str(error), rawPlanText=raw_plan_text)
        fallback_plan = _build_rule_based_fallback_plan(text, table, request)
        if fallback_plan is not None:
            validate_expense_query_plan(fallback_plan, table)
            _log_expense_query_event("expense_query_plan_fallback_used", parsedPlan=_query_plan_to_log_dict(fallback_plan), fallbackType="rule_based")
            return fallback_plan
        raise


def fetch_current_month_expense_table(now: datetime | None = None) -> ExpenseTable:
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
                range=f"'{sheet_name}'!A:Z",
            )
            .execute()
        )
    except HttpError as error:
        if error.resp.status == 400:
            return ExpenseTable(sheet_name=sheet_name, headers=STANDARD_HEADERS, rows=[])
        raise SheetsError(f"Google Sheetsから集計データを取得できませんでした: {error}") from error
    except Exception as error:
        raise SheetsError(f"Google Sheetsから集計データを取得できませんでした: {error}") from error

    return parse_expense_table(result.get("values", []), sheet_name)


def parse_expense_table(values: list[list[object]], sheet_name: str) -> ExpenseTable:
    if not values:
        return ExpenseTable(sheet_name=sheet_name, headers=STANDARD_HEADERS, rows=[])

    headers = [_cell(values[0], index) for index in range(len(values[0]))]
    rows: list[dict[str, str]] = []
    for value_row in values[1:]:
        row: dict[str, str] = {}
        for index, header in enumerate(headers):
            if header:
                row[header] = _cell(value_row, index)
        if any(row.values()):
            rows.append(row)
    return ExpenseTable(sheet_name=sheet_name, headers=headers, rows=rows)


def execute_expense_query_plan(
    plan: ExpenseQueryPlan,
    table: ExpenseTable,
    request: ExpenseQueryRequest,
) -> AggregationResult:
    validate_expense_query_plan(plan, table)
    filtered_rows = [row for row in table.rows if _matches_filters(row, plan.filters, request)]
    metric_type = str(plan.metric.get("type"))
    metric_column = str(plan.metric.get("column") or "")

    groups: dict[tuple[str, ...], int] = {}
    labels: dict[tuple[str, ...], str] = {}
    matched_labels_by_group: dict[tuple[str, ...], set[str]] = {}
    for row in filtered_rows:
        group_key = tuple(row.get(column, "") for column in plan.group_by)
        parsed = _parse_total(row.get(metric_column, ""))
        if parsed is None:
            continue
        value = parsed

        groups[group_key] = groups.get(group_key, 0) + value
        labels.setdefault(group_key, _group_label(row, group_key, plan))
        for filter_plan in plan.filters:
            if filter_plan.get("column") == "店舗名":
                matched_labels_by_group.setdefault(group_key, set()).add(row.get("店舗名", ""))

    result_groups = [
        AggregationGroup(
            label=labels.get(group_key, ""),
            value=value,
            matched_labels=sorted(label for label in matched_labels_by_group.get(group_key, set()) if label),
        )
        for group_key, value in groups.items()
    ]
    result_groups = _sort_groups(result_groups, plan)
    return AggregationResult(plan=plan, groups=result_groups)


def validate_expense_query_plan(plan: ExpenseQueryPlan, table: ExpenseTable) -> None:
    headers = set(table.headers)
    metric_type = str(plan.metric.get("type") or "")
    metric_column = str(plan.metric.get("column") or "")
    if metric_type not in ALLOWED_METRIC_TYPES:
        raise UnsupportedExpenseQueryError("metric type is not supported")
    if metric_column and metric_column not in headers:
        raise UnsupportedExpenseQueryError("metric column does not exist")
    if metric_type == "sum" and metric_column not in NUMERIC_COLUMNS:
        raise UnsupportedExpenseQueryError("sum metric column is not numeric")

    for column in [*plan.group_by, *plan.display_columns]:
        if column not in headers:
            raise UnsupportedExpenseQueryError("group/display column does not exist")

    for filter_plan in plan.filters:
        column = str(filter_plan.get("column") or "")
        operator = str(filter_plan.get("operator") or "")
        if column not in headers:
            raise UnsupportedExpenseQueryError("filter column does not exist")
        if operator == "contains_normalized":
            if column not in {"店舗名", "LINE表示名"}:
                raise UnsupportedExpenseQueryError("contains_normalized is only supported for store or display name")
            if not _filter_literal_value(filter_plan):
                raise UnsupportedExpenseQueryError("contains_normalized requires value")
        elif operator != "equals":
            raise UnsupportedExpenseQueryError("filter operator is not supported")

        value_from = filter_plan.get("valueFrom")
        if value_from is not None and str(value_from) not in ALLOWED_VALUE_FROM:
            raise UnsupportedExpenseQueryError("valueFrom is not supported")
        if column == "LINEユーザーID" and value_from is None:
            raise UnsupportedExpenseQueryError("LINE user id filter requires valueFrom")
        if value_from is None and "value" not in filter_plan:
            raise UnsupportedExpenseQueryError("filter value is missing")

    for sort_plan in plan.sort:
        if str(sort_plan.get("by") or "") not in {"metric", "group"}:
            raise UnsupportedExpenseQueryError("sort target is not supported")
        if str(sort_plan.get("direction") or "desc") not in {"asc", "desc"}:
            raise UnsupportedExpenseQueryError("sort direction is not supported")


def build_aggregation_reply(result: AggregationResult, request: ExpenseQueryRequest, now: datetime) -> str:
    month = _current_month_sheet_name(now)
    if not result.groups:
        return f"{month} の条件に一致する登録はありません。"

    plan = result.plan
    if not plan.group_by:
        total = result.groups[0].value
        store_filter = _store_filter_value(plan.filters)
        if _has_line_user_id_filter(plan.filters):
            name = request.line_display_name or "あなた"
            if store_filter:
                return f"{month} の{name}さんの{store_filter}を含む支出合計は {total:,}円です。{_matched_labels_suffix(result.groups[0])}"
            return f"{month} の{name}さんの合計は {total:,}円です。"
        if store_filter:
            return f"{month} の{store_filter}を含む支出合計は {total:,}円です。{_matched_labels_suffix(result.groups[0])}"
        return f"{month} の全体合計は {total:,}円です。"

    title = _group_title(plan.group_by)
    lines = [f"{month} の{title}です。"]
    for group in result.groups:
        lines.append(f"{group.label}: {group.value:,}円")
    return "\n".join(lines)


def _parse_request(payload: dict) -> ExpenseQueryRequest:
    return ExpenseQueryRequest(
        line_user_id=str(payload["lineUserId"]),
        line_display_name=str(payload.get("lineDisplayName") or ""),
        line_message_id=str(payload["lineMessageId"]),
        text=str(payload["text"]),
    )


def _build_deterministic_query_plan(
    text: str,
    table: ExpenseTable,
    request: ExpenseQueryRequest | None,
) -> ExpenseQueryPlan | None:
    if not {"LINEユーザーID", "合計金額"}.issubset(set(table.headers)):
        return None
    if _is_self_query(text, request):
        return _self_total_plan()
    return None


def _build_rule_based_fallback_plan(
    text: str,
    table: ExpenseTable,
    request: ExpenseQueryRequest | None,
) -> ExpenseQueryPlan | None:
    self_plan = _build_deterministic_query_plan(text, table, request)
    if self_plan is not None:
        return self_plan
    display_name_plan = _build_display_name_search_fallback_plan(text, table)
    if display_name_plan is not None:
        return display_name_plan
    return _build_store_search_fallback_plan(text, table)


def _self_total_plan() -> ExpenseQueryPlan:
    return ExpenseQueryPlan(
        metric={"type": "sum", "column": "合計金額"},
        group_by=[],
        display_columns=[],
        filters=[{"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineUserId"}],
        sort=[],
    )


def _is_self_query(text: str, request: ExpenseQueryRequest | None) -> bool:
    normalized_text = _normalize_search_text(text)
    if any(token in normalized_text for token in ["自分", "私", "わたし", "俺", "おれ", "僕", "ぼく"]):
        return True
    if request and request.line_display_name:
        display_name = _normalize_search_text(request.line_display_name)
        if display_name and display_name in normalized_text:
            return True
    return False


def _build_display_name_search_fallback_plan(text: str, table: ExpenseTable) -> ExpenseQueryPlan | None:
    if not {"LINE表示名", "合計金額"}.issubset(set(table.headers)):
        return None
    display_name = _extract_display_name_search_keyword(text)
    if not display_name:
        return None
    return ExpenseQueryPlan(
        metric={"type": "sum", "column": "合計金額"},
        group_by=[],
        display_columns=[],
        filters=[{"column": "LINE表示名", "operator": "contains_normalized", "value": display_name}],
        sort=[],
    )


def _build_store_search_fallback_plan(text: str, table: ExpenseTable) -> ExpenseQueryPlan | None:
    if not {"店舗名", "合計金額"}.issubset(set(table.headers)):
        return None
    store = _extract_store_search_keyword(text)
    if not store:
        return None
    return ExpenseQueryPlan(
        metric={"type": "sum", "column": "合計金額"},
        group_by=[],
        display_columns=[],
        filters=[{"column": "店舗名", "operator": "contains_normalized", "value": store}],
        sort=[],
    )


def _extract_display_name_search_keyword(text: str) -> str:
    normalized_text = unicodedata.normalize("NFKC", text).strip()
    normalized_text = re.sub(r"[?？!！。]+$", "", normalized_text)
    if not re.search(r"(いくら|幾ら|金額|合計|払|使)", normalized_text):
        return ""

    patterns = [
        r"(?P<name>.+?)(?:さん|ちゃん)?の(?:合計|金額|支出).*",
        r"(?P<name>.+?)(?:さん|ちゃん)?(?:はいくら|は幾ら).*",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized_text)
        if not match:
            continue
        name = _cleanup_display_name_search_keyword(match.group("name"))
        if name:
            return name
    return ""


def _cleanup_display_name_search_keyword(value: str) -> str:
    name = value.strip(" 「」『』\"'")
    name = re.sub(r"(さん|ちゃん)$", "", name)
    if not name or name in {"今月", "自分", "私", "俺", "僕", "うち"} or "指定" in name:
        return ""
    return name


def _extract_store_search_keyword(text: str) -> str:
    normalized_text = unicodedata.normalize("NFKC", text).strip()
    normalized_text = re.sub(r"[?？!！。]+$", "", normalized_text)
    if not re.search(r"(いくら|幾ら|金額|合計|払|使)", normalized_text):
        return ""

    patterns = [
        r"(?P<store>.+?)の店舗(?:で|に|の)?.*",
        r"(?P<store>.+?)(?:で|に)(?:いくら|幾ら|どれくらい|どのくらい|どんくらい|何円|合計|金額|払|使).*",
        r"(?P<store>.+?)(?:はいくら|は幾ら|の合計|の金額).*",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, normalized_text)
        if not match:
            continue
        store = _cleanup_store_search_keyword(match.group("store"))
        if store:
            return store
    return ""


def _cleanup_store_search_keyword(value: str) -> str:
    store = value.strip()
    store = re.sub(r"^(今月|自分|私|俺|僕|うち|わたし|おれ|ぼく)の", "", store)
    store = re.sub(r"(さん|ちゃん)$", "", store)
    store = store.strip(" 「」『』\"'")
    if not store or store in {"今月", "自分", "私", "俺", "僕"} or "指定" in store:
        return ""
    return store


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


def _parse_query_plan(parsed: dict) -> ExpenseQueryPlan:
    if parsed.get("unsupported") is True:
        raise UnsupportedExpenseQueryError("unsupported query")
    target_month = parsed.get("targetMonth")
    if target_month is not None and target_month != "current":
        raise UnsupportedExpenseQueryError("target month is not supported")
    metric = parsed.get("metric")
    if not isinstance(metric, dict):
        raise UnsupportedExpenseQueryError("metric is missing")
    return ExpenseQueryPlan(
        metric=metric,
        group_by=_required_string_list(parsed, "groupBy"),
        display_columns=_required_string_list(parsed, "displayColumns"),
        filters=_normalize_query_filters(_required_dict_list(parsed, "filters")),
        sort=_required_dict_list(parsed, "sort"),
    )


def _normalize_query_filters(filters: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized_filters: list[dict[str, object]] = []
    for filter_plan in filters:
        normalized_filter = dict(filter_plan)
        if (
            normalized_filter.get("column") == "LINEユーザーID"
            and normalized_filter.get("operator") == "equals"
            and _is_line_user_id_value_from_alias(normalized_filter.get("value"))
        ):
            normalized_filter.pop("value", None)
            normalized_filter["valueFrom"] = "lineUserId"
        normalized_filters.append(normalized_filter)
    return normalized_filters


def _is_line_user_id_value_from_alias(value: object) -> bool:
    return str(value or "") in {"lineUserId", "request.lineUserId", "request.line_user_id"}


def _required_string_list(parsed: dict, key: str) -> list[str]:
    value = parsed.get(key)
    if not isinstance(value, list):
        raise UnsupportedExpenseQueryError(f"{key} must be a list")
    return [str(item) for item in value if str(item)]


def _required_dict_list(parsed: dict, key: str) -> list[dict[str, object]]:
    value = parsed.get(key)
    if not isinstance(value, list):
        raise UnsupportedExpenseQueryError(f"{key} must be a list")
    if any(not isinstance(item, dict) for item in value):
        raise UnsupportedExpenseQueryError(f"{key} must contain objects")
    return [item for item in value if isinstance(item, dict)]


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


def _matches_filters(row: dict[str, str], filters: list[dict[str, object]], request: ExpenseQueryRequest) -> bool:
    for filter_plan in filters:
        column = str(filter_plan.get("column") or "")
        operator = str(filter_plan.get("operator") or "")
        expected = _filter_value(filter_plan, request)
        actual = row.get(column, "")
        if operator == "equals" and actual != expected:
            return False
        if operator == "contains_normalized" and _normalize_search_text(expected) not in _normalize_search_text(actual):
            return False
    return True


def _filter_value(filter_plan: dict[str, object], request: ExpenseQueryRequest) -> str:
    if filter_plan.get("valueFrom") == "lineUserId":
        return request.line_user_id
    return _filter_literal_value(filter_plan)


def _filter_literal_value(filter_plan: dict[str, object]) -> str:
    return str(filter_plan.get("value") or "")


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = normalized.replace("lawson", "ローソン")
    normalized = _katakana_to_hiragana(normalized)
    normalized = re.sub(r"(株式会社|\(株\)|（株）)", "", normalized)
    normalized = re.sub(r"[\s\-_・.,、。/\\]+", "", normalized)
    return normalized


def _katakana_to_hiragana(value: str) -> str:
    return "".join(chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char for char in value)


def _group_label(row: dict[str, str], group_key: tuple[str, ...], plan: ExpenseQueryPlan) -> str:
    if plan.group_by == ["LINEユーザーID"]:
        for display_column in plan.display_columns:
            display_value = row.get(display_column, "")
            if display_value:
                return display_value
        return _short_user_id(group_key[0])
    if not group_key:
        return ""
    return " / ".join(value or "未入力" for value in group_key)


def _sort_groups(groups: list[AggregationGroup], plan: ExpenseQueryPlan) -> list[AggregationGroup]:
    if not plan.sort:
        return sorted(groups, key=lambda group: (-group.value, group.label))

    sort_plan = plan.sort[0]
    reverse = str(sort_plan.get("direction") or "desc") == "desc"
    if sort_plan.get("by") == "group":
        return sorted(groups, key=lambda group: group.label, reverse=reverse)
    if reverse:
        return sorted(groups, key=lambda group: (-group.value, group.label))
    return sorted(groups, key=lambda group: (group.value, group.label))


def _group_title(group_by: list[str]) -> str:
    if group_by == ["LINEユーザーID"]:
        return "ユーザー別合計"
    if group_by == ["カテゴリ"]:
        return "カテゴリ別合計"
    if group_by == ["店舗名"]:
        return "店舗別合計"
    return "集計結果"


def _store_filter_value(filters: list[dict[str, object]]) -> str:
    for filter_plan in filters:
        if filter_plan.get("column") == "店舗名":
            return str(filter_plan.get("value") or "")
    return ""


def _has_line_user_id_filter(filters: list[dict[str, object]]) -> bool:
    return any(filter_plan.get("column") == "LINEユーザーID" and filter_plan.get("valueFrom") == "lineUserId" for filter_plan in filters)


def _matched_labels_suffix(group: AggregationGroup) -> str:
    if not group.matched_labels:
        return ""
    return f"\n対象: {', '.join(group.matched_labels)}"


def _unsupported_reply() -> str:
    return "今月の自分の合計、全体合計、ユーザー別合計、カテゴリ別合計、店舗別合計、店舗名検索に答えられます。"


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


def _log_expense_query_event(event: str, **context: object) -> None:
    sanitized_context = {key: _sanitize_for_log(value) for key, value in context.items()}
    logger.info(
        "expense_query_event %s",
        json.dumps({"event": event, **sanitized_context}, ensure_ascii=False, sort_keys=True),
    )


def _sanitize_for_log(value: object) -> object:
    if isinstance(value, ExpenseQueryPlan):
        return _query_plan_to_log_dict(value)
    if isinstance(value, dict):
        return {str(key): _sanitize_for_log(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _query_plan_to_log_dict(plan: ExpenseQueryPlan) -> dict[str, object]:
    return {
        "metric": _sanitize_for_log(plan.metric),
        "groupBy": _sanitize_for_log(plan.group_by),
        "displayColumns": _sanitize_for_log(plan.display_columns),
        "filters": _sanitize_for_log(plan.filters),
        "sort": _sanitize_for_log(plan.sort),
    }


def _redact_sensitive_text(value: str) -> str:
    return LINE_USER_ID_PATTERN.sub("[REDACTED_LINE_USER_ID]", value)
