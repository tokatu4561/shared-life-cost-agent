# レシート読み取りLINE Agent デプロイ準備

## 概要
AWSへのデプロイは手動で実行する。リポジトリ側では、CDK synth/deployできる構成、Lambda/AgentCoreのソース、Secrets Managerから実値を取得する実装を用意する。

リージョンは `ap-northeast-1`、環境名は `prod` とする。

## 事前に必要なローカル環境
- Node.js 20以上 と npm 9以上
- AWS CLI
- Docker
- AWS CDK bootstrap済みのAWSアカウント
- `ap-northeast-1` でBedrock、AgentCore、Secrets Manager、S3、SQS、DynamoDB、Lambdaを作成できる権限
- Google Cloud ProjectでCloud Vision APIとGoogle Sheets APIを有効化済みであること

## CDK確認コマンド
既存のSecrets Manager Secretを使う場合は、`infra/.env.example` を `infra/.env` にコピーし、Secret名を設定する。`.env` はGit管理しない。

```bash
cd infra
npm install
npm test
npm run synth
```

問題なければ、任意のタイミングで以下を実行する。

```bash
cd infra
npm run cdk -- deploy
```

## Secrets Manager
CDKは以下のSecretを作成する。デプロイ後、実値で更新する。

`infra/.env` にSecret名を指定した場合、CDKはSecretを新規作成せず、既存Secretを参照する。

| Secret名 | 値 |
|---|---|
| `receipt-line-agent/prod/line` | LINE Messaging APIの設定JSON |
| `receipt-line-agent/prod/google` | Google Sheetsの設定JSON |

アプリ内部では、LINEとGoogle Sheetsに必要な値をSecrets Managerから取得する。

LINE Secretの例:

```json
{
  "channelSecret": "LINE Channel Secret",
  "channelAccessToken": "LINE Channel Access Token",
  "channelId": "任意。アプリでは未使用",
  "allowedExpenseQuerySourceIds": ["集計質問を許可するLINEグループID"]
}
```

`allowedExpenseQuerySourceIds` は集計質問の情報漏えい防止に使う。本アプリの集計質問は1つのLINEグループでのみ使う前提のため、許可するグループIDだけを設定する。未設定または空配列の場合、テキスト集計質問は拒否される。

Google Secretの例:

```json
{
  "spreadsheetId": "Google Spreadsheet ID",
  "serviceAccount": {
    "type": "service_account",
    "project_id": "...",
    "private_key_id": "...",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "...",
    "client_id": "..."
  }
}
```

## LINE設定
CDK deploy後、Stack Outputの `WebhookUrl` をLINE DevelopersのWebhook URLに設定する。

BotはPush Messageを使うため、利用者がBotを友だち追加している必要がある。

## Google Sheets設定
- Google Sheets APIを有効化する。
- Service Accountを作成する。
- Service Account JSON全文を `receipt-line-agent/prod/google` の `serviceAccount` に保存する。
- 対象スプレッドシートをService Accountのメールアドレスへ編集権限で共有する。
- スプレッドシートIDを `receipt-line-agent/prod/google` の `spreadsheetId` に保存する。

月別シート名は `yyyy-MM` 形式とする。例: `2026-05`

## Cloud Vision設定
- Google Secretの `serviceAccount` はGoogle Sheets転記とCloud Vision OCRの両方で利用する。
- Service Accountの `project_id` が属するGoogle Cloud ProjectでCloud Vision APIを有効化する。
- Cloud Vision APIの `images.annotate` は `https://www.googleapis.com/auth/cloud-vision` または `https://www.googleapis.com/auth/cloud-platform` のOAuthスコープを要求する。このアプリは `cloud-vision` スコープでService Account認証を行う。
- このアプリは画像bytesをAWS S3から読み込んでVision APIへ送るため、Google Cloud StorageのObject Viewer権限は不要。Google Cloud Storage URIをVision APIへ渡す構成に変更する場合のみ、Service Accountへ `roles/storage.objectViewer` を付与する。
- `PERMISSION_DENIED` が出る場合は、Cloud Vision APIの有効化、Service Accountの無効化有無、組織ポリシー、課金設定を確認する。

## トラブルシュート
- AgentCore Runtimeで `secretsmanager:GetSecretValue` の `AccessDeniedException` が出る場合は、最新のCDKを再デプロイし、AgentCore Runtime実行ロールにGoogle Secretの読み取り権限が付与されていることを確認する。
- 既存Secretを `infra/.env` の `GOOGLE_SECRET_NAME` で参照する場合、値はARNではなくSecret名を指定する。例: `receipt-line-agent/prod/google`
- Secrets Managerの実体ARNには末尾にランダムsuffixが付くため、CDKではSecret名ARNとsuffix付きARNの両方に一致するIAM policyを生成する。
- AgentCore Runtimeで `bedrock:InvokeModel` の `AccessDeniedException` が出て、対象Resourceが `foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0` の場合は、デプロイ済みRuntimeが古いモデルIDを使っている。`BEDROCK_MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0` を反映するため、最新のCDKとAgentイメージを再デプロイする。
- Bedrock Inference Profile経由のfoundation model権限は、`bedrock:InferenceProfileArn` 条件キーで絞る。AWS公式ドキュメント本文には `aws:InferenceProfileArn` と書かれた箇所があるが、Service Authorization Referenceと公式JSON例では `bedrock:InferenceProfileArn` が使われている。

## セキュリティ方針
- レシート画像はS3の `receipts/*` のみ公開読み取りを許可する。AWSアカウントレベルのS3 Block Public AccessでPublic Policyがブロックされている場合はデプロイ前に対象方針を確認する。
- Google Sheetsへの追記は `RAW` で行い、OCR/LLM由来の文字列を数式として評価させない。
- LINE Push Messageには内部例外の詳細を含めない。ユーザーには固定の失敗メッセージを返し、詳細はDynamoDB/CloudWatchで確認する。
- テキスト集計質問はLINEグループからのみ受け付け、LINE Secretの `allowedExpenseQuerySourceIds` に含まれるグループIDからのみ許可する。
- BedrockとAgentCoreのIAM権限は、利用するClaude Haiku 4.5 Inference Profile、対応するfoundation model、対象AgentCore Runtimeに絞る。

## 固定仕様
- AWSリージョン: `ap-northeast-1`
- S3レシート画像保持期間: 90日
- Lambda CloudWatch Logs保持期間: 30日
- Bedrockモデル: Claude Haiku 4.5のGlobal Inference Profile ID `global.anthropic.claude-haiku-4-5-20251001-v1:0`
- Sheets列: `登録日時`, `レシート日付`, `LINE表示名`, `LINEユーザーID`, `店舗名`, `カテゴリ`, `合計金額`, `画像URL`, `LINEメッセージID`
- カテゴリ: `食費`, `日用品`, `その他`
