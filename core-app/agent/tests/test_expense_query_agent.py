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
    from src.expense_query_agent import ExpenseQueryPlan, ExpenseQueryRequest, ExpenseTable


class ExpenseQueryAgentTest(unittest.TestCase):
    def test_missing_month_sheet_returns_empty_table(self) -> None:
        service = _fake_sheets_service(FakeHttpError(400))
        with (
            patch.object(expense_query_agent, "get_google_secret", return_value={}),
            patch.object(expense_query_agent, "spreadsheet_id", return_value="spreadsheet-id"),
            patch.object(expense_query_agent, "_build_sheets_service", return_value=service),
        ):
            table = expense_query_agent.fetch_current_month_expense_table(datetime(2026, 5, 13, tzinfo=timezone.utc))

        self.assertEqual(table.sheet_name, "2026-05")
        self.assertEqual(table.headers, expense_query_agent.STANDARD_HEADERS)
        self.assertEqual(table.rows, [])

    def test_empty_sheet_still_rejects_unsupported_query(self) -> None:
        with (
            patch.object(expense_query_agent, "fetch_current_month_expense_table", return_value=_expense_table([])),
            patch.object(expense_query_agent, "build_expense_query_plan", side_effect=expense_query_agent.UnsupportedExpenseQueryError),
        ):
            result = expense_query_agent.process_expense_query(
                {"lineUserId": "U001", "lineDisplayName": "太郎", "lineMessageId": "m1", "text": "先月の合計は？"}
            )

        self.assertEqual(result["status"], "unsupported")

    def test_empty_sheet_returns_no_registration_for_supported_query(self) -> None:
        plan = ExpenseQueryPlan(
            metric={"type": "sum", "column": "合計金額"},
            group_by=[],
            display_columns=[],
            filters=[],
            sort=[],
        )
        with (
            patch.object(expense_query_agent, "fetch_current_month_expense_table", return_value=_expense_table([])),
            patch.object(expense_query_agent, "build_expense_query_plan", return_value=plan),
        ):
            result = expense_query_agent.process_expense_query(
                {"lineUserId": "U001", "lineDisplayName": "太郎", "lineMessageId": "m1", "text": "今月全部でいくら？"}
            )

        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["replyMessage"], "2026-05 の登録はまだありません。")

    def test_parses_table_from_header_row(self) -> None:
        table = expense_query_agent.parse_expense_table(
            [
                ["登録日時", "LINE表示名", "LINEユーザーID", "店舗名", "合計金額"],
                ["2026-05-01", "太郎", "'U001", "ローソン 渋谷店", "1,200"],
            ],
            "2026-05",
        )

        self.assertEqual(table.headers, ["登録日時", "LINE表示名", "LINEユーザーID", "店舗名", "合計金額"])
        self.assertEqual(
            table.rows,
            [
                {
                    "登録日時": "2026-05-01",
                    "LINE表示名": "太郎",
                    "LINEユーザーID": "U001",
                    "店舗名": "ローソン 渋谷店",
                    "合計金額": "1,200",
                }
            ],
        )

    def test_executes_self_total_plan_with_value_from_line_user_id(self) -> None:
        table = _expense_table(
            [
                {"LINE表示名": "太郎", "LINEユーザーID": "U001", "店舗名": "ローソン", "カテゴリ": "食費", "合計金額": "1,200"},
                {"LINE表示名": "花子", "LINEユーザーID": "U002", "店舗名": "ローソン", "カテゴリ": "食費", "合計金額": "800"},
            ]
        )
        plan = ExpenseQueryPlan(
            metric={"type": "sum", "column": "合計金額"},
            group_by=[],
            display_columns=[],
            filters=[{"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineUserId"}],
            sort=[],
        )

        result = expense_query_agent.execute_expense_query_plan(
            plan,
            table,
            ExpenseQueryRequest("U001", "太郎", "m1", "自分はいくら？"),
        )

        self.assertEqual(result.groups, [expense_query_agent.AggregationGroup(label="", value=1200, matched_labels=[])])

    def test_builds_self_plan_without_llm_for_self_pronoun(self) -> None:
        bedrock_runtime = MagicMock()

        with patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime):
            plan = expense_query_agent.build_expense_query_plan(
                "自分の合計はいくら？",
                _expense_table([]),
                ExpenseQueryRequest("U001", "リョウタ", "m1", "自分の合計はいくら？"),
            )

        bedrock_runtime.invoke_model.assert_not_called()
        self.assertEqual(plan.filters, [{"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineUserId"}])

    def test_builds_self_plan_without_llm_for_own_display_name(self) -> None:
        bedrock_runtime = MagicMock()

        with patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime):
            plan = expense_query_agent.build_expense_query_plan(
                "リョウタの合計はいくら？",
                _expense_table([]),
                ExpenseQueryRequest("U001", "リョウタ", "m1", "リョウタの合計はいくら？"),
            )

        bedrock_runtime.invoke_model.assert_not_called()
        self.assertEqual(plan.filters, [{"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineUserId"}])

    def test_display_name_filter_uses_normalized_contains(self) -> None:
        table = _expense_table(
            [
                {"LINE表示名": "リョウタ", "LINEユーザーID": "U001", "店舗名": "ローソン", "カテゴリ": "食費", "合計金額": "1,200"},
                {"LINE表示名": "りょうた", "LINEユーザーID": "U002", "店舗名": "セブン", "カテゴリ": "食費", "合計金額": "300"},
                {"LINE表示名": "花子", "LINEユーザーID": "U003", "店舗名": "セブン", "カテゴリ": "食費", "合計金額": "700"},
            ]
        )
        plan = ExpenseQueryPlan(
            metric={"type": "sum", "column": "合計金額"},
            group_by=[],
            display_columns=[],
            filters=[{"column": "LINE表示名", "operator": "contains_normalized", "value": "リョウタ"}],
            sort=[],
        )

        result = expense_query_agent.execute_expense_query_plan(
            plan,
            table,
            ExpenseQueryRequest("U999", "別人", "m1", "リョウタの合計は？"),
        )

        self.assertEqual(result.groups, [expense_query_agent.AggregationGroup(label="", value=1500, matched_labels=[])])

    def test_builds_display_name_fallback_plan_when_llm_marks_unsupported(self) -> None:
        table = _expense_table([])
        response_body = {"content": [{"text": '{"unsupported":true}'}]}
        bedrock_runtime = MagicMock()
        bedrock_runtime.invoke_model.return_value = {"body": BytesIO(json.dumps(response_body).encode("utf-8"))}

        with patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime):
            plan = expense_query_agent.build_expense_query_plan(
                "リョウタの合計はいくら？",
                table,
                ExpenseQueryRequest("U999", "別人", "m1", "リョウタの合計はいくら？"),
            )

        self.assertEqual(
            plan,
            ExpenseQueryPlan(
                metric={"type": "sum", "column": "合計金額"},
                group_by=[],
                display_columns=[],
                filters=[{"column": "LINE表示名", "operator": "contains_normalized", "value": "リョウタ"}],
                sort=[],
            ),
        )

    def test_executes_by_user_total_using_user_id_and_display_name(self) -> None:
        table = _expense_table(
            [
                {"LINE表示名": "太郎", "LINEユーザーID": "U001", "店舗名": "ローソン", "カテゴリ": "食費", "合計金額": "1,200"},
                {"LINE表示名": "別名", "LINEユーザーID": "U001", "店舗名": "セブン", "カテゴリ": "食費", "合計金額": "300"},
                {"LINE表示名": "花子", "LINEユーザーID": "U002", "店舗名": "セブン", "カテゴリ": "食費", "合計金額": "700"},
            ]
        )
        plan = ExpenseQueryPlan(
            metric={"type": "sum", "column": "合計金額"},
            group_by=["LINEユーザーID"],
            display_columns=["LINE表示名"],
            filters=[],
            sort=[{"by": "metric", "direction": "desc"}],
        )

        result = expense_query_agent.execute_expense_query_plan(
            plan,
            table,
            ExpenseQueryRequest("U001", "太郎", "m1", "ユーザー別で"),
        )

        self.assertEqual(
            result.groups,
            [
                expense_query_agent.AggregationGroup(label="太郎", value=1500, matched_labels=[]),
                expense_query_agent.AggregationGroup(label="花子", value=700, matched_labels=[]),
            ],
        )

    def test_store_filter_uses_normalized_contains(self) -> None:
        table = _expense_table(
            [
                {"LINE表示名": "太郎", "LINEユーザーID": "U001", "店舗名": "ローソン 渋谷店", "カテゴリ": "食費", "合計金額": "1,200"},
                {"LINE表示名": "花子", "LINEユーザーID": "U002", "店舗名": "LAWSON", "カテゴリ": "食費", "合計金額": "800"},
                {"LINE表示名": "花子", "LINEユーザーID": "U002", "店舗名": "セブン", "カテゴリ": "食費", "合計金額": "700"},
            ]
        )
        plan = ExpenseQueryPlan(
            metric={"type": "sum", "column": "合計金額"},
            group_by=[],
            display_columns=[],
            filters=[{"column": "店舗名", "operator": "contains_normalized", "value": "ローソン"}],
            sort=[],
        )

        result = expense_query_agent.execute_expense_query_plan(
            plan,
            table,
            ExpenseQueryRequest("U001", "太郎", "m1", "ローソンはいくら？"),
        )

        self.assertEqual(result.groups, [expense_query_agent.AggregationGroup(label="", value=2000, matched_labels=["LAWSON", "ローソン 渋谷店"])])

    def test_builds_store_search_fallback_plan_when_llm_marks_unsupported(self) -> None:
        table = _expense_table([])
        response_body = {"content": [{"text": '{"unsupported":true}'}]}
        bedrock_runtime = MagicMock()
        bedrock_runtime.invoke_model.return_value = {"body": BytesIO(json.dumps(response_body).encode("utf-8"))}

        with patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime):
            plan = expense_query_agent.build_expense_query_plan("ニトリの店舗でいくらぐらい払ってる？", table)

        self.assertEqual(
            plan,
            ExpenseQueryPlan(
                metric={"type": "sum", "column": "合計金額"},
                group_by=[],
                display_columns=[],
                filters=[{"column": "店舗名", "operator": "contains_normalized", "value": "ニトリ"}],
                sort=[],
            ),
        )

    def test_normalizes_line_user_id_literal_to_value_from(self) -> None:
        plan = expense_query_agent._parse_query_plan(
            {
                "metric": {"type": "sum", "column": "合計金額"},
                "groupBy": [],
                "displayColumns": [],
                "filters": [{"column": "LINEユーザーID", "operator": "equals", "value": "lineUserId"}],
                "sort": [],
            }
        )

        self.assertEqual(plan.filters, [{"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineUserId"}])

    def test_rejects_line_user_id_literal_filter_after_normalization(self) -> None:
        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent.validate_expense_query_plan(
                ExpenseQueryPlan(
                    metric={"type": "sum", "column": "合計金額"},
                    group_by=[],
                    display_columns=[],
                    filters=[{"column": "LINEユーザーID", "operator": "equals", "value": "U001"}],
                    sort=[],
                ),
                _expense_table([]),
            )

    def test_logs_redacted_raw_and_parsed_query_plan(self) -> None:
        table = _expense_table([])
        response_body = {
            "content": [
                {
                    "text": json.dumps(
                        {
                            "metric": {"type": "sum", "column": "合計金額"},
                            "groupBy": [],
                            "displayColumns": [],
                            "filters": [{"column": "LINEユーザーID", "operator": "equals", "value": "U00123456789abcdef"}],
                            "sort": [],
                        }
                    )
                }
            ]
        }
        bedrock_runtime = MagicMock()
        bedrock_runtime.invoke_model.return_value = {"body": BytesIO(json.dumps(response_body).encode("utf-8"))}

        with (
            patch.object(expense_query_agent.boto3, "client", return_value=bedrock_runtime),
            patch.object(expense_query_agent.logger, "info") as logger_info,
        ):
            with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
                expense_query_agent.build_expense_query_plan("ID指定の合計は？", table)

        logged_messages = "\n".join(str(call.args) for call in logger_info.call_args_list)
        self.assertIn("[REDACTED_LINE_USER_ID]", logged_messages)
        self.assertNotIn("U00123456789abcdef", logged_messages)

    def test_rejects_invalid_query_plan(self) -> None:
        table = _expense_table([])

        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent.validate_expense_query_plan(
                ExpenseQueryPlan(
                    metric={"type": "sum", "column": "存在しない列"},
                    group_by=[],
                    display_columns=[],
                    filters=[],
                    sort=[],
                ),
                table,
            )

        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent.validate_expense_query_plan(
                ExpenseQueryPlan(
                    metric={"type": "sum", "column": "合計金額"},
                    group_by=[],
                    display_columns=[],
                    filters=[{"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineDisplayName"}],
                    sort=[],
                ),
                table,
            )

        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent.validate_expense_query_plan(
                ExpenseQueryPlan(
                    metric={"type": "count", "column": "合計金額"},
                    group_by=[],
                    display_columns=[],
                    filters=[],
                    sort=[],
                ),
                table,
            )

        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent._parse_query_plan(
                {
                    "targetMonth": "2026-04",
                    "metric": {"type": "sum", "column": "合計金額"},
                    "groupBy": [],
                    "displayColumns": [],
                    "filters": [],
                    "sort": [],
                }
            )

        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent._parse_query_plan(
                {
                    "metric": {"type": "sum", "column": "合計金額"},
                    "groupBy": [],
                    "displayColumns": [],
                    "filters": {"column": "LINEユーザーID", "operator": "equals", "valueFrom": "lineUserId"},
                    "sort": [],
                }
            )

        with self.assertRaises(expense_query_agent.UnsupportedExpenseQueryError):
            expense_query_agent.validate_expense_query_plan(
                ExpenseQueryPlan(
                    metric={"type": "sum", "column": "合計金額"},
                    group_by=[],
                    display_columns=[],
                    filters=[{"column": "店舗名", "operator": "contains_normalized", "value": ""}],
                    sort=[],
                ),
                table,
            )


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


def _expense_table(rows: list[dict[str, str]]) -> ExpenseTable:
    headers = ["LINE表示名", "LINEユーザーID", "店舗名", "カテゴリ", "合計金額"]
    return ExpenseTable(sheet_name="2026-05", headers=headers, rows=rows)


if __name__ == "__main__":
    unittest.main()
