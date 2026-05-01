# AWS Lambda デプロイガイド

このドキュメントでは、日本技術ニュース分析システムをAWS Lambdaにデプロイする手順を説明します。

## 前提条件

### 必要なツール
- AWS CLI（設定済み）
- Python 3.11+
- zip コマンド

### AWS権限
以下のAWSサービスへのアクセス権限が必要です:
- Lambda（関数作成・更新、Layer公開）
- S3（バケット作成、オブジェクト読み書き）
- IAM（ロール作成・管理）
- EventBridge（ルール作成）
- CloudWatch Logs（ログ確認）

---

## デプロイ手順

### ステップ1: S3バケット作成

```bash
# S3バケットを作成
aws s3 mb s3://claude-news-analyzer --region ap-northeast-1

# バケットポリシーを設定（必要に応じて）
# Lambda関数からのアクセスを許可
```

### ステップ2: 設定ファイルをS3にアップロード

```bash
# config.jsonをS3にアップロード
aws s3 cp config/config.json s3://claude-news-analyzer/config/config.json

# news_analysis_prompt.txtをS3にアップロード
aws s3 cp config/news_analysis_prompt.txt s3://claude-news-analyzer/config/news_analysis_prompt.txt

# アップロード確認
aws s3 ls s3://claude-news-analyzer/config/
```

### ステップ3: IAMロール作成

Lambda実行用のIAMロールを作成します。

**信頼ポリシー（deploy/policies/trust-policy.json）:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**権限ポリシー（deploy/policies/permissions-policy.json）:**
このポリシーには、S3へのアクセス権限、CloudWatch Logsへの書き込み権限、およびAmazon Bedrockのモデルを呼び出すための権限が含まれています。
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::claude-news-analyzer/config/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::claude-news-analyzer/responses/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:*:*:inference-profile/*",
        "arn:aws:bedrock:*::foundation-model/*"
      ]
    }
  ]
}
```

**ロール作成コマンド:**
```bash
# IAMロールを作成
aws iam create-role \
  --role-name lambda-claude-news-analyzer \
  --assume-role-policy-document file://deploy/policies/trust-policy.json

# 権限ポリシーをアタッチ
aws iam put-role-policy \
  --role-name lambda-claude-news-analyzer \
  --policy-name claude-news-analyzer-permissions \
  --policy-document file://deploy/policies/permissions-policy.json

# ロールARNを取得（後で使用）
aws iam get-role --role-name lambda-claude-news-analyzer --query 'Role.Arn' --output text
```

### ステップ4: Lambda Layer構築

依存パッケージをLambda Layer形式でパッケージングします。

```bash
# Lambda Layerを構築
./deploy/build_layer.sh

# 出力ファイル: lambda-layer.zip (約35-40MB)
```

### ステップ5: Lambda関数デプロイ

環境変数を設定してデプロイスクリプトを実行します。

```bash
# 環境変数を設定
export LAMBDA_ROLE_ARN="arn:aws:iam::235217802903:role/lambda-claude-news-analyzer"
export S3_BUCKET_NAME="claude-news-analyzer"
export AWS_REGION="ap-northeast-1"

# デプロイ実行
./deploy/deploy.sh
```

### ステップ6: Lambda環境変数を設定

S3バケット名を環境変数として設定します。

```bash
# Lambda環境変数を設定
aws lambda update-function-configuration \
  --function-name claude-news-analyzer \
  --environment "Variables={S3_BUCKET_NAME=claude-news-analyzer}" \
  --region ap-northeast-1
```

**注**: このシステムはAmazon BedrockをIAMロール経由で利用するため、APIキー（`CLAUDE_API_KEY`）の設定は不要です。


### ステップ7: Lambda関数をテスト実行

```bash
# テストイベントでLambda関数を実行
  AWS_MAX_ATTEMPTS=1 aws lambda invoke \
    --function-name claude-news-analyzer \
    --region ap-northeast-1 \
    --cli-read-timeout 900 \
    --cli-connect-timeout 10 \
    output.json

# 実行結果を確認
cat output.json

# CloudWatch Logsを確認
aws logs tail /aws/lambda/claude-news-analyzer --follow
```

### ステップ8: EventBridgeスケジュールを設定

毎日0:00 UTC（= 9:00 JST）に自動実行するスケジュールを設定します。

```bash
# EventBridgeルールを作成
aws events put-rule \
  --name claude-news-analyzer-daily \
  --schedule-expression 'cron(0 0 * * ? *)' \
  --state ENABLED \
  --region ap-northeast-1

# Lambda関数をターゲットに追加
# まず、Lambda関数のARNを取得
LAMBDA_ARN=$(aws lambda get-function \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --query 'Configuration.FunctionArn' \
  --output text)

# EventBridgeターゲットを追加
aws events put-targets \
  --rule claude-news-analyzer-daily \
  --targets "Id=1,Arn=${LAMBDA_ARN}" \
  --region ap-northeast-1

# Lambda関数にEventBridge実行権限を付与
aws lambda add-permission \
  --function-name claude-news-analyzer \
  --statement-id claude-news-analyzer-daily-event \
  --action 'lambda:InvokeFunction' \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-northeast-1:235217802903:rule/claude-news-analyzer-daily \
  --region ap-northeast-1
```

---

## 動作確認

### Lambda関数の動作確認

```bash
# 手動実行
AWS_MAX_ATTEMPTS=1 aws lambda invoke \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --cli-read-timeout 900 \
  --cli-connect-timeout 10 \
  output.json

# 実行結果
cat output.json
```

**期待される出力:**
```json
{
  "statusCode": 200,
  "body": "{\"success\": true, \"message\": \"ニュース分析が正常に完了しました\"}"
}
```

### S3に保存された結果を確認

```bash
# 今日の結果ファイルを確認
TODAY=$(date +%Y-%m-%d)
aws s3 ls s3://claude-news-analyzer/responses/${TODAY}

# ファイルをダウンロードして確認
aws s3 cp s3://claude-news-analyzer/responses/${TODAY}.txt ./
aws s3 cp s3://claude-news-analyzer/responses/${TODAY}_articles.txt ./

cat ${TODAY}.txt
```

### CloudWatch Logsを確認

```bash
# 最新ログを表示
aws logs tail /aws/lambda/claude-news-analyzer --follow

# または、AWS Management Consoleで確認
# https://console.aws.amazon.com/cloudwatch/home?region=ap-northeast-1#logsV2:log-groups/log-group/$252Faws$252Flambda$252Fclaude-news-analyzer
```

---

## トラブルシューティング

### エラー: Lambda関数がタイムアウトする

**原因**: 記事数が多すぎる、または処理が遅い

**解決策**:
1. `config.json`の`max_articles_per_site`を減らす（30 → 20）
2. Lambdaタイムアウトを15分に設定（既に設定済み）
3. `parallel_content_workers`を増やす（5 → 10）

### エラー: S3アクセス拒否

**原因**: IAMロールの権限不足

**解決策**:
```bash
# IAMロールに権限を追加
aws iam put-role-policy \
  --role-name lambda-claude-news-analyzer \
  --policy-name s3-access \
  --policy-document file://deploy/policies/permissions-policy.json
```

### エラー: Lambda Layerが大きすぎる

**原因**: 依存パッケージのサイズが50MBを超えている

**解決策**:
1. S3経由でアップロード:
```bash
# S3にアップロード
aws s3 cp lambda-layer.zip s3://claude-news-analyzer/layers/lambda-layer.zip

# S3からLambda Layerを公開
aws lambda publish-layer-version \
  --layer-name claude-news-analyzer-dependencies \
  --content S3Bucket=claude-news-analyzer,S3Key=layers/lambda-layer.zip \
  --compatible-runtimes python3.11 \
  --region ap-northeast-1
```

2. または、コンテナイメージデプロイに移行

---

## コスト見積もり

### 月額コスト（30日運用）

| サービス | 使用量 | 料金 |
|---------|--------|------|
| Lambda | 9,000秒/月 × 1.5GB | $0.23 |
| S3 | 6MB ストレージ + 120リクエスト | $0.001 |
| CloudWatch Logs | 30MB/月 | $0.02 |
| **合計** | | **約$0.25/月** |

※ Secrets Manager使用時は +$0.40/月

---

## ロールバック手順

Lambda移行後に問題が発生した場合、以下の手順でcronに戻せます。

```bash
# 1. EventBridgeスケジュールを無効化
aws events disable-rule --name claude-news-analyzer-daily --region ap-northeast-1

# 2. ローカル環境でcronを再有効化
crontab -e
# 以下の行を追加:
# 0 9 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 claude_fetcher.py >> logs/cron.log 2>&1

# 3. S3からデータをローカルにコピー（必要に応じて）
aws s3 sync s3://claude-news-analyzer/responses/ ./responses/

# 4. ローカル環境で手動実行してテスト
python3 claude_fetcher.py
```

**所要時間**: 約15分

---

## 参考資料

- [AWS Lambda公式ドキュメント](https://docs.aws.amazon.com/lambda/)
- [AWS Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html)
- [EventBridge スケジュール式](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html)
- [CloudWatch Logs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/)

---

## サポート

問題が発生した場合は、以下を確認してください:

1. CloudWatch Logsでエラーメッセージを確認
2. Lambda関数の環境変数が正しく設定されているか確認
3. IAMロールの権限が正しいか確認
4. S3バケットに設定ファイルが存在するか確認

それでも解決しない場合は、このリポジトリのIssueを作成してください。
