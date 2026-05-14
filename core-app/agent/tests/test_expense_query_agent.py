from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import types
import unittest
from unittest.mock import MagicMock, patch

fake_googleapiclient = types.ModuleType("googleapiclient")
fake_googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
fake_googleapiclient_discovery.build = MagicMock()
fake_googleapiclient_errors = types.ModuleType("googleapiclient.errors")


class FakeHttpError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__("http error")
        self.resp = types.SimpleNamespace(status=status)


fake_googleapiclient_errors.HttpError = FakeHttpError
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
        "googleapiclient.errors": fake_googleapiclient_errors,
    },
):
    from src import expense_query_agent
    from src.expense_query_agent import ExpenseQueryRequest, ExpenseRow


class ExpenseQueryAgentTest(unittest.TestCase):
    def test_classifies_supported_intent(self) -> None:
        response_body = {"content": [{"text": '{"intent":"by_user_total"}'}]}
        bedrock_runtime = MagicMock()
        bedrock_runtime.invoke_model.return_value = {"body": BytesIO(json.dumps(response_body).encode("utf-8"))}

        with patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime):
            self.assertEqual(expense_query_agent.classify_expense_query("ユーザーごとの金額は？"), "by_user_total")

    def test_classifies_unknown_intent_as_unsupported(self) -> None:
        response_body = {"content": [{"text": '{"intent":"store_total"}'}]}
        bedrock_runtime = MagicMock()
        bedrock_runtime.invoke_model.return_value = {"body": BytesIO(json.dumps(response_body).encode("utf-8"))}

        with patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime):
            self.assertEqual(expense_query_agent.classify_expense_query("店舗別で出して"), "unsupported")

    def test_parses_expense_rows_and_ignores_invalid_totals(self) -> None:
        values = [
            ["登録日時", "レシート日付", "LINE表示名", "LINEユーザーID", "店舗名", "カテゴリ", "合計金額"],
            ["", "", "太郎", "'U001", "", "", "1,200"],
            ["", "", "花子", "U002", "", "", "abc"],
            ["", "", "花子", "U002", "", "", "300円"],
            ["", "", "名無し", "", "", "", "999"],
        ]

        self.assertEqual(
            expense_query_agent.parse_expense_rows(values),
            [
                ExpenseRow(line_display_name="太郎", line_user_id="U001", total=1200),
                ExpenseRow(line_display_name="花子", line_user_id="U002", total=300),
            ],
        )

    def test_builds_overall_total_reply(self) -> None:
        reply = expense_query_agent.build_expense_query_reply(
            "overall_total",
            [
                ExpenseRow("太郎", "U001", 1200),
                ExpenseRow("花子", "U002", 300),
            ],
            ExpenseQueryRequest("U001", "太郎", "m1", "今月全部でいくら？"),
            datetime(2026, 5, 13, tzinfo=timezone.utc),
        )

        self.assertEqual(reply, "2026-05 の全体合計は 1,500円です。")

    def test_builds_self_total_reply(self) -> None:
        reply = expense_query_agent.build_expense_query_reply(
            "self_total",
            [
                ExpenseRow("太郎", "U001", 1200),
                ExpenseRow("花子", "U002", 300),
            ],
            ExpenseQueryRequest("U001", "太郎", "m1", "自分はいくら？"),
            datetime(2026, 5, 13, tzinfo=timezone.utc),
        )

        self.assertEqual(reply, "2026-05 の太郎さんの合計は 1,200円です。")

    def test_builds_by_user_total_reply(self) -> None:
        reply = expense_query_agent.build_expense_query_reply(
            "by_user_total",
            [
                ExpenseRow("太郎", "U001", 1200),
                ExpenseRow("花子", "U002", 300),
                ExpenseRow("", "U002", 400),
            ],
            ExpenseQueryRequest("U001", "太郎", "m1", "ユーザーごとは？"),
            datetime(2026, 5, 13, tzinfo=timezone.utc),
        )

        self.assertEqual(reply, "2026-05 のユーザー別合計です。\n太郎: 1,200円\n花子: 700円")

    def test_missing_month_sheet_returns_empty_rows(self) -> None:
        service = _fake_sheets_service(FakeHttpError(400))
        with (
            patch.object(expense_query_agent, "get_google_secret", return_value={}),
            patch.object(expense_query_agent, "spreadsheet_id", return_value="spreadsheet-id"),
            patch.object(expense_query_agent, "_build_sheets_service", return_value=service),
        ):
            self.assertEqual(expense_query_agent.fetch_current_month_expenses(), [])


def _fake_sheets_service(execute_result: object):
    execute = MagicMock()
    if isinstance(execute_result, Exception):
        execute.side_effect = execute_result
    else:
        execute.return_value = execute_result

    get = MagicMock(return_value=types.SimpleNamespace(execute=execute))
    values = MagicMock(return_value=types.SimpleNamespace(get=get))
    spreadsheets = MagicMock(return_value=types.SimpleNamespace(values=values))
    return types.SimpleNamespace(spreadsheets=spreadsheets)


if __name__ == "__main__":
    unittest.main()
