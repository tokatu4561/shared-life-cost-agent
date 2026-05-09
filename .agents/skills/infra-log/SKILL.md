---
name: aws-log-investigation
description: AWSのログ調査を行うときに使うSkill。CloudWatch Logs、Lambda、ECS、ALB、WAF、CloudTrailなどを参照専用権限で調査する。AWSリソースの作成・更新・削除・デプロイは禁止。
---

# AWSログ調査Skill

## 目的

このSkillは、AWS上のログや実行状況を **参照専用** で調査するためのものです。

対象例:

- CloudWatch Logs
- Lambdaログ
- ECS / Fargateログ
- ALBアクセスログ
- WAFログ
- CloudTrailイベント
- API Gatewayログ
- CloudFrontに関連するログ

## 絶対に守るルール

このSkillでは、**読み取り専用の操作のみ** を行ってください。

AWSリソースの作成・更新・削除・デプロイ・設定変更は禁止です。

以下のようなコマンドは絶対に実行してはいけません。

```bash
aws cloudformation deploy
aws cloudformation delete-stack
aws cloudformation update-stack
aws cdk deploy
aws cdk destroy
cdk deploy
cdk destroy
aws lambda update-function-configuration
aws lambda update-function-code
aws ecs update-service
aws s3 rm
aws iam create-role
aws iam put-role-policy
aws iam attach-role-policy
aws iam delete-role
aws logs delete-log-group
aws logs delete-log-stream
aws logs put-log-events
```

上記に含まれていなくても、**読み取り専用かどうか判断できないコマンドは実行しないでください**。

## 使用するAWSプロファイル

AWS CLIを実行する場合は、必ず以下のプロファイルを使用してください。

```bash
--profile log-investigator
```

調査コマンドを実行する前に、必ず現在のAWS認証情報を確認してください。

```bash
aws sts get-caller-identity \
  --profile log-investigator \
  --region ap-northeast-1
```

期待するロールは以下です。

```text
arn:aws:sts::<ACCOUNT_ID>:user/ai-aws-cli-user
```

もし期待するロールではない場合は、調査を止めてユーザーに確認してください。

## リージョン

デフォルトリージョンは以下です。

```text
ap-northeast-1
```

AWS CLIを使う場合は、原則として明示的にリージョンを指定してください。

```bash
--region ap-northeast-1
```

## 調査の進め方

1. 調査対象のサービス、リソース名、ロググループ、時間帯を確認する
2. `sts get-caller-identity` でAWS認証情報を確認する
3. 読み取り専用コマンドだけを使う
4. できるだけ狭い時間範囲で調査する
5. アカウント全体検索ではなく、特定のロググループを優先する
6. 結果を以下の観点で整理する
   - 調査した時間帯
   - 実行したコマンド
   - 関連するログ
   - 推定原因
   - 確度
   - 次に確認すべき読み取り専用の調査

## よく使うコマンド

### 認証情報の確認

```bash
aws sts get-caller-identity \
  --profile log-investigator \
  --region ap-northeast-1
```

### ロググループの検索

```bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/YOUR_PREFIX" \
  --profile log-investigator \
  --region ap-northeast-1
```

### ログイベントの検索

```bash
aws logs filter-log-events \
  --log-group-name "/aws/lambda/YOUR_FUNCTION_NAME" \
  --start-time START_TIME_MS \
  --end-time END_TIME_MS \
  --filter-pattern "ERROR" \
  --profile log-investigator \
  --region ap-northeast-1
```

### CloudWatch Logs Insights のクエリ開始

```bash
aws logs start-query \
  --log-group-name "/aws/lambda/YOUR_FUNCTION_NAME" \
  --start-time START_TIME_SECONDS \
  --end-time END_TIME_SECONDS \
  --query-string 'fields @timestamp, @message | sort @timestamp desc | limit 50' \
  --profile log-investigator \
  --region ap-northeast-1
```

### CloudWatch Logs Insights の結果取得

```bash
aws logs get-query-results \
  --query-id QUERY_ID \
  --profile log-investigator \
  --region ap-northeast-1
```

### ECSサービスの確認

```bash
aws ecs describe-services \
  --cluster YOUR_CLUSTER_NAME \
  --services YOUR_SERVICE_NAME \
  --profile log-investigator \
  --region ap-northeast-1
```

### ECSタスクの確認

```bash
aws ecs describe-tasks \
  --cluster YOUR_CLUSTER_NAME \
  --tasks YOUR_TASK_ID \
  --profile log-investigator \
  --region ap-northeast-1
```

### ALBターゲットヘルス確認

```bash
aws elbv2 describe-target-health \
  --target-group-arn YOUR_TARGET_GROUP_ARN \
  --profile log-investigator \
  --region ap-northeast-1
```

### CloudTrailイベントの確認

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateFunctionCode \
  --start-time "2026-05-09T00:00:00+09:00" \
  --end-time "2026-05-09T23:59:59+09:00" \
  --profile log-investigator \
  --region ap-northeast-1
```

## 出力時のルール

調査結果を報告するときは、以下を含めてください。

- 何を確認したか
- どの時間帯を確認したか
- どのコマンドを使ったか
- 見つかったログ
- 見つからなかったこと
- 推定原因
- 確度
- 次に確認すべき読み取り専用の調査

## 注意点

ログだけで原因を断定できない場合は、断定しないでください。

例えば以下のように表現してください。

- 「このログからは〇〇の可能性が高いです」
- 「ただし、△△のログがないため断定はできません」
- 「次に□□を確認すると切り分けできます」

## 禁止事項

以下は禁止です。

- AWSリソースの作成
- AWSリソースの更新
- AWSリソースの削除
- CDK deploy
- CDK destroy
- CloudFormationの更新・削除
- IAMポリシーやロールの変更
- S3オブジェクトの削除
- CloudWatch Logsの削除
- 本番環境への変更操作

## 推奨運用

このSkillを使う場合は、ログ調査用のIAMロールと、CDKデプロイ用のIAMロールを分けてください。

ログ調査用ロールには、原則として以下のような参照専用権限だけを付与します。

- CloudWatch Logs の参照
- CloudWatch Logs Insights の実行と結果取得
- CloudTrail の参照
- ECS / Lambda / ALB / CloudFront などの Describe / Get / List 系権限
- 必要に応じた S3 ログバケットの GetObject / ListBucket

以下のような権限は付与しないでください。

- `iam:*`
- `cloudformation:*`
- `s3:DeleteObject`
- `logs:DeleteLogGroup`
- `logs:PutLogEvents`
- `lambda:UpdateFunctionCode`
- `lambda:UpdateFunctionConfiguration`
- `ecs:UpdateService`
- `cloudfront:UpdateDistribution`
- `wafv2:UpdateWebACL`

## IAMロールの前提

このSkillでは、以下のようなAWS CLIプロファイルが設定済みであることを前提とします。

```ini
[profile log-investigator]
role_arn = arn:aws:iam::<ACCOUNT_ID>:role/CodexLogInvestigatorRole
source_profile = default
region = ap-northeast-1
```

## 調査結果テンプレート

調査結果は、原則として以下の形式でまとめてください。

```md
## 調査概要

- 対象:
- 時間帯:
- 使用したAWSプロファイル:
- 使用したリージョン:

## 実行した確認

### 1. 認証情報確認

実行コマンド:

```bash
aws sts get-caller-identity --profile log-investigator --region ap-northeast-1
```

結果:

- 想定ロールだったか:
- Account:
- Arn:

### 2. ログ確認

実行コマンド:

```bash
# 実行したコマンドを記載
```

結果:

- 見つかったログ:
- 見つからなかったログ:
- 気になるエラー:

## 推定原因

- 可能性が高い原因:
- 根拠:
- 断定できない点:

## 次に確認するべきこと

- 次の読み取り専用確認:
- 必要であれば人間が確認すべき変更操作:
```

## 重要な方針

このSkillは、ログ調査を補助するためのものです。

AWS環境を変更する判断や実行は、このSkillでは行いません。

変更が必要だと考えられる場合も、実行せずに、ユーザーへ提案として伝えてください。
