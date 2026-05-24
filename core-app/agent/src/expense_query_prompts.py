from __future__ import annotations

import json


def build_query_plan_prompt(text: str, sheet_name: str, headers: list[str]) -> str:
    return (
        "あなたはLINE家計精算Agentの集計プラン作成器です。\n"
        "ユーザーの質問を、Google Sheetsの今月シートに対する読み取り専用の集計DSL JSONに変換してください。\n"
        "計算は実行側のコードが行うため、結果の金額は計算しないでください。\n"
        "返答は説明なしのJSONのみです。\n"
        "v1で許可するmetric.typeは sum のみです。sumの列は原則「合計金額」です。\n"
        "本人を表す「自分」「私」「俺」などは LINEユーザーID equals valueFrom lineUserId にしてください。\n"
        "ユーザー別集計は LINEユーザーID でgroupByし、displayColumnsに LINE表示名 を指定してください。\n"
        "店舗名検索は 店舗名 contains_normalized value にしてください。例: 「イオンの店舗でいくらぐらい払ってる？」は value を「イオン」にしてください。\n"
        "月指定、全期間、更新、削除、修正依頼、対応できない質問は {\"unsupported\":true} を返してください。\n"
        "形式: {\"metric\":{\"type\":\"sum\",\"column\":\"列名\"},\"groupBy\":[\"列名\"],\"displayColumns\":[\"列名\"],\"filters\":[{\"column\":\"列名\",\"operator\":\"equals|contains_normalized\",\"value\":\"文字列\",\"valueFrom\":\"lineUserId\"}],\"sort\":[{\"by\":\"metric|group\",\"direction\":\"asc|desc\"}]}\n\n"
        f"今月シート名: {sheet_name}\n"
        f"列定義: {json.dumps(headers, ensure_ascii=False)}\n"
        f"質問:\n{text}"
    )


def build_classification_prompt(text: str) -> str:
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
