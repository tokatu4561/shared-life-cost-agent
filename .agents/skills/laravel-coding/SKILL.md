---
name: laravel-coding-conventions
description: Laravelのグローバルスコープのコーディング規約。プロジェクトスコープのルールがある場合はそちらを優先する。Laravelプロジェクトでコードを書く、レビューする、リファクタリングする際に参照する。PHP/Laravelのコード生成・編集・レビュー時に自動的に適用する。命名規則、モデル、コントローラー、ビュー、バッチ処理、Enum、日付処理、テストコードなどの規約を含む。
---

# Laravel Coding Conventions

Laravelプロジェクト向けグローバルスコープのコーディング規約スキル。コード生成・編集・レビュー時にこの規約に従う。プロジェクトスコープのルールがある場合はそちらを優先する。

## 規約の適用

Laravelコードを生成・編集・レビューする際、以下の詳細リファレンスを参照し、規約に従ったコードを出力する。

### 主要な規約サマリ

- **命名規則**: PSR-12準拠、Laravel命名規則に従う（コントローラは単数形、ルートは複数形、変数はキャメルケース等）
- **モデル**: 1対1リレーションは`$with`でイーガーローディング、`getXXXAttribute`は使わず通常メソッドを使う、N+1問題に注意
- **コントローラー**: 1つのbladeを複数コントローラーで共用しない
- **ビュー**: ビューコンポーザは使わずミドルウェアを使う、bladeで複雑な条件文やモデル呼び出しをしない、Laravel Collectiveでフォーム生成
- **バッチ処理**: ステートレスを意識
- **その他**: Enumを使う、ネスト三項演算子禁止、日付は`Date`ファサードを使う（`Carbon`直接利用不可）
- **テスト**: AAAパターン、テスト間の独立性、RefreshDatabase、モック活用、assertTrueを避ける

### 詳細リファレンス

コード例や詳細な説明は以下のリファレンスを参照する。

- [references/naming-conventions.md](references/naming-conventions.md) - 命名規則
- [references/model.md](references/model.md) - モデル規約
- [references/controller.md](references/controller.md) - コントローラー規約
- [references/view.md](references/view.md) - ビュー規約
- [references/batch.md](references/batch.md) - バッチ処理規約
- [references/others.md](references/others.md) - その他（Enum、三項演算子、日付）
- [references/testing-structure.md](references/testing-structure.md) - テスト：構造と命名規則
- [references/testing-isolation.md](references/testing-isolation.md) - テスト：テスト間の独立性
- [references/testing-writing.md](references/testing-writing.md) - テスト：テストの書き方
- [references/testing-config.md](references/testing-config.md) - テスト：設定・運用
