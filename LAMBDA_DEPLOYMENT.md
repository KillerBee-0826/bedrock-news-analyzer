# AWS Lambda デプロイガイド

このドキュメントでは、日本技術ニュース分析システムを AWS Lambda にデプロイする手順を説明します。
上から順に実行することで、日次・週次・月次分析まで動作する状態にします。

## 前提条件

### 必要なツール
- AWS CLI（設定済み）
- Docker（Lambda Layer 構築用）
- Python 3.11+
- zip コマンド

### AWS権限
以下の AWS サービスへのアクセス権限が必要です。
- Lambda（関数作成・更新、Layer 公開）
- S3（バケット作成、オブジェクト読み書き）
- IAM（ロール作成・管理）
- EventBridge（ルール作成）
- CloudWatch Logs（ログ確認）
- Bedrock（モデル呼び出し）

---

## デプロイ手順

### ステップ1: S3バケット作成

```bash
# S3バケットを作成
aws s3 mb s3://claude-news-analyzer --region ap-northeast-1

# 作成確認
aws s3 ls s3://claude-news-analyzer/
```

### ステップ2: 設定ファイルとプロンプトをS3にアップロード

日次・週次・月次で別々のプロンプトを使用します。Lambda は `config/config.json` の `prompt_paths` を参照して、`analysis_type` ごとに読み込むプロンプトを切り替えます。

```bash
# config.jsonをS3にアップロード
aws s3 cp config/config.json s3://claude-news-analyzer/config/config.json

# 日次・週次・月次プロンプトをS3にアップロード
aws s3 cp config/news_analysis_prompt.txt s3://claude-news-analyzer/config/news_analysis_prompt.txt
aws s3 cp config/weekly_news_analysis_prompt.txt s3://claude-news-analyzer/config/weekly_news_analysis_prompt.txt
aws s3 cp config/monthly_news_analysis_prompt.txt s3://claude-news-analyzer/config/monthly_news_analysis_prompt.txt

# アップロード確認
aws s3 ls s3://claude-news-analyzer/config/
```

### ステップ3: IAMロール作成

Lambda 実行用の IAM ロールを作成します。

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

このポリシーには、S3 へのアクセス権限、CloudWatch Logs への書き込み権限、および Amazon Bedrock のモデルを呼び出すための権限が含まれています。

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
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::claude-news-analyzer/responses/*",
        "arn:aws:s3:::claude-news-analyzer/daily/*",
        "arn:aws:s3:::claude-news-analyzer/weekly/*",
        "arn:aws:s3:::claude-news-analyzer/monthly/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::claude-news-analyzer"
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

# ロールARNを取得（ステップ5で使用）
aws iam get-role \
  --role-name lambda-claude-news-analyzer \
  --query 'Role.Arn' \
  --output text
```

既存ロールを更新する場合は、`create-role` は実行せず、`put-role-policy` だけを実行してください。

### ステップ4: Lambda Layer構築

依存パッケージを Lambda Layer 形式でパッケージングします。

```bash
# Lambda Layerを構築
./deploy/build_layer.sh

# 出力ファイル確認
ls -lh lambda-layer.zip
```

`lambda-layer.zip` が Lambda の直接アップロード上限を超える場合は、後述の「Lambda Layerが大きすぎる」を参照してください。

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

再デプロイ時も Lambda 関数を削除する必要はありません。`deploy/deploy.sh` は既存の `claude-news-analyzer` がある場合、`update-function-code` と `update-function-configuration` で更新します。

`CreateFunction` で `Function already exist` が出る場合は、既存確認が正しく通っていない可能性があります。削除する前に以下を確認してください。

```bash
# 実行中のAWSアカウントを確認
aws sts get-caller-identity

# 対象リージョンに関数が存在するか確認
aws lambda get-function \
  --function-name claude-news-analyzer \
  --region ap-northeast-1
```

`get-function` が権限不足や認証エラーで失敗している場合、関数が存在していても新規作成扱いに見えることがあります。その場合は `lambda:GetFunction`, `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration` 権限と `AWS_REGION` を確認してください。

### ステップ6: Lambda環境変数を確認・更新

`deploy/deploy.sh` は `S3_BUCKET_NAME` と `TZ=Asia/Tokyo` を設定します。必要に応じて明示的に再設定します。

```bash
# Lambda環境変数を設定
aws lambda update-function-configuration \
  --function-name claude-news-analyzer \
  --environment "Variables={S3_BUCKET_NAME=claude-news-analyzer,TZ=Asia/Tokyo}" \
  --region ap-northeast-1

# 設定確認
aws lambda get-function-configuration \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --query 'Environment.Variables'
```

このシステムは Amazon Bedrock を IAM ロール経由で利用するため、API キーの設定は不要です。

### ステップ7: Lambda関数をテスト実行

まず日次分析を手動実行します。結果は `daily/` プレフィックスに保存されます。

```bash
# 日次分析を手動実行
AWS_MAX_ATTEMPTS=1 aws lambda invoke \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --cli-read-timeout 900 \
  --cli-connect-timeout 10 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"analysis_type":"daily"}' \
  output-daily.json

# 実行結果を確認
cat output-daily.json

# CloudWatch Logsを確認
aws logs tail /aws/lambda/claude-news-analyzer --follow
```

週次・月次は前段のレポートが S3 に存在する必要があります。入力データがある状態で以下を実行します。

```bash
# 週次分析を手動実行
AWS_MAX_ATTEMPTS=1 aws lambda invoke \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --cli-read-timeout 900 \
  --cli-connect-timeout 10 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"analysis_type":"weekly"}' \
  output-weekly.json

cat output-weekly.json

# 月次分析を手動実行
AWS_MAX_ATTEMPTS=1 aws lambda invoke \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --cli-read-timeout 900 \
  --cli-connect-timeout 10 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"analysis_type":"monthly"}' \
  output-monthly.json

cat output-monthly.json
```

### ステップ8: EventBridgeスケジュールを設定

同じ Lambda 関数に対して、日次・週次・月次の 3 つの EventBridge ルールを作成します。各ターゲットの `Input` で `analysis_type` を渡します。

```bash
# Lambda関数のARNを取得
LAMBDA_ARN=$(aws lambda get-function \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --query 'Configuration.FunctionArn' \
  --output text)

# 日次: 毎日0:00 UTC（= 9:00 JST）
aws events put-rule \
  --name claude-news-analyzer-daily \
  --schedule-expression 'cron(0 0 * * ? *)' \
  --state ENABLED \
  --region ap-northeast-1

cat > /tmp/claude-news-analyzer-daily-target.json <<EOF
[
  {
    "Id": "1",
    "Arn": "${LAMBDA_ARN}",
    "Input": "{\"analysis_type\":\"daily\"}"
  }
]
EOF

aws events put-targets \
  --rule claude-news-analyzer-daily \
  --targets file:///tmp/claude-news-analyzer-daily-target.json \
  --region ap-northeast-1

aws lambda add-permission \
  --function-name claude-news-analyzer \
  --statement-id claude-news-analyzer-daily-event \
  --action 'lambda:InvokeFunction' \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-northeast-1:235217802903:rule/claude-news-analyzer-daily \
  --region ap-northeast-1

# 週次: 毎週日曜1:00 UTC（= 日曜10:00 JST）
aws events put-rule \
  --name claude-news-analyzer-weekly \
  --schedule-expression 'cron(0 1 ? * SUN *)' \
  --state ENABLED \
  --region ap-northeast-1

cat > /tmp/claude-news-analyzer-weekly-target.json <<EOF
[
  {
    "Id": "1",
    "Arn": "${LAMBDA_ARN}",
    "Input": "{\"analysis_type\":\"weekly\"}"
  }
]
EOF

aws events put-targets \
  --rule claude-news-analyzer-weekly \
  --targets file:///tmp/claude-news-analyzer-weekly-target.json \
  --region ap-northeast-1

aws lambda add-permission \
  --function-name claude-news-analyzer \
  --statement-id claude-news-analyzer-weekly-event \
  --action 'lambda:InvokeFunction' \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-northeast-1:235217802903:rule/claude-news-analyzer-weekly \
  --region ap-northeast-1

# 月次: 毎月1日2:00 UTC（= 11:00 JST）
aws events put-rule \
  --name claude-news-analyzer-monthly \
  --schedule-expression 'cron(0 2 1 * ? *)' \
  --state ENABLED \
  --region ap-northeast-1

cat > /tmp/claude-news-analyzer-monthly-target.json <<EOF
[
  {
    "Id": "1",
    "Arn": "${LAMBDA_ARN}",
    "Input": "{\"analysis_type\":\"monthly\"}"
  }
]
EOF

aws events put-targets \
  --rule claude-news-analyzer-monthly \
  --targets file:///tmp/claude-news-analyzer-monthly-target.json \
  --region ap-northeast-1

aws lambda add-permission \
  --function-name claude-news-analyzer \
  --statement-id claude-news-analyzer-monthly-event \
  --action 'lambda:InvokeFunction' \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:ap-northeast-1:235217802903:rule/claude-news-analyzer-monthly \
  --region ap-northeast-1
```

既に同じ `statement-id` の権限が存在する場合、`add-permission` は失敗します。その場合は既存権限を確認し、必要に応じて `remove-permission` 後に再実行してください。

```bash
aws lambda get-policy \
  --function-name claude-news-analyzer \
  --region ap-northeast-1
```

---

## 動作確認

### Lambda関数の動作確認

```bash
# 日次分析を手動実行
AWS_MAX_ATTEMPTS=1 aws lambda invoke \
  --function-name claude-news-analyzer \
  --region ap-northeast-1 \
  --cli-read-timeout 900 \
  --cli-connect-timeout 10 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"analysis_type":"daily"}' \
  output-daily.json

cat output-daily.json
```

**期待される出力:**

```json
{
  "statusCode": 200,
  "body": "{\"success\": true, \"message\": \"daily ニュース分析が正常に完了しました\"}"
}
```

### S3に保存された結果を確認

```bash
# 日次結果を確認
TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)
aws s3 ls s3://claude-news-analyzer/daily/
aws s3 cp s3://claude-news-analyzer/daily/${TODAY}.txt ./
aws s3 cp s3://claude-news-analyzer/daily/${TODAY}_articles.txt ./
cat ${TODAY}.txt

# 週次結果を確認
aws s3 ls s3://claude-news-analyzer/weekly/

# 月次結果を確認
aws s3 ls s3://claude-news-analyzer/monthly/
```

週次分析は、前週の日曜から土曜までの記事分析を対象にします。日次ファイルは実行日ベースのため、対象記事日付の翌日ファイルを `daily/` から読み込みます。移行期間の互換用として、`responses/YYYY-MM-DD.txt` も読み取り対象になります。

月次分析は、前月内に終了日を持つ週次分析を `weekly/` から読み込みます。

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

**原因**: 記事数が多すぎる、本文取得に時間がかかる、または Bedrock 応答待ちが長い。

**解決策**:
1. `config/config.json` の `max_articles_per_site` を減らす（30 → 20）
2. Lambda タイムアウトを 15 分に設定する（`deploy/deploy.sh` では 900 秒）
3. `parallel_content_workers` を調整する（5 → 10 など）
4. `bedrock_read_timeout` が 600 秒以上になっているか確認する

### エラー: S3アクセス拒否

**原因**: IAM ロールの権限不足。

**解決策**:

```bash
# IAMロールに最新の権限を反映
aws iam put-role-policy \
  --role-name lambda-claude-news-analyzer \
  --policy-name claude-news-analyzer-permissions \
  --policy-document file://deploy/policies/permissions-policy.json
```

以下のプレフィックスに対する権限が必要です。
- `config/*`: 設定とプロンプト読み込み
- `daily/*`: 日次分析と記事一覧の読み書き
- `weekly/*`: 週次分析の読み書き
- `monthly/*`: 月次分析の書き込み
- `responses/*`: 旧日次分析の読み取り互換

### エラー: 週次分析の入力となる日次分析が見つからない

**原因**: 前週日曜から土曜までの記事分析に対応する日次ファイルが `daily/` または旧 `responses/` に存在しない。

**確認コマンド**:

```bash
aws s3 ls s3://claude-news-analyzer/daily/
aws s3 ls s3://claude-news-analyzer/responses/
```

必要な日次分析を先に実行するか、対象期間のファイルが S3 に存在するか確認してください。

### エラー: 月次分析の入力となる週次分析が見つからない

**原因**: 前月内に終了日を持つ週次分析ファイルが `weekly/` に存在しない。

**確認コマンド**:

```bash
aws s3 ls s3://claude-news-analyzer/weekly/
```

月次分析の対象になる週次ファイル名は `weekly/YYYY-MM-DD_YYYY-MM-DD.txt` です。後半の日付が前月内にあるものが月次分析に使われます。

### エラー: CreateFunctionでFunction already existになる

**原因**: 既存 Lambda 関数がある状態で新規作成処理に進んでいる。

**解決策**:

```bash
# アカウントとリージョンを確認
aws sts get-caller-identity
aws lambda get-function \
  --function-name claude-news-analyzer \
  --region ap-northeast-1

# 通常は削除せず、デプロイスクリプトで更新する
export LAMBDA_ROLE_ARN="arn:aws:iam::235217802903:role/lambda-claude-news-analyzer"
export S3_BUCKET_NAME="claude-news-analyzer"
export AWS_REGION="ap-northeast-1"
./deploy/deploy.sh
```

Lambda 関数を削除して再作成するのは通常手順ではありません。削除すると EventBridge 権限やトリガー設定を再確認する必要があります。

### エラー: Lambda Layerが大きすぎる

**原因**: 依存パッケージのサイズが Lambda の直接アップロード上限を超えている。

**解決策**:

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

公開された Layer ARN を Lambda 関数に設定してください。

---

## コスト見積もり

### 月額コスト（30日運用）

日次 30 回、週次 4-5 回、月次 1 回の実行を想定します。Bedrock の利用料金はモデルと入出力トークン量に依存するため、ここでは Lambda/S3/CloudWatch の概算のみ記載します。

| サービス | 使用量 | 料金 |
|---------|--------|------|
| Lambda | 約10,000-12,000秒/月 × 1.5GB | 約$0.25-0.30 |
| S3 | 数十MBストレージ + 数百リクエスト | 約$0.01未満 |
| CloudWatch Logs | 数十MB/月 | 約$0.02 |
| Bedrock | モデルとトークン量に依存 | 別途確認 |

---

## ロールバック手順

Lambda 移行後に問題が発生した場合、以下の手順でスケジュール実行を止めます。

```bash
# 1. EventBridgeスケジュールを無効化
aws events disable-rule --name claude-news-analyzer-daily --region ap-northeast-1
aws events disable-rule --name claude-news-analyzer-weekly --region ap-northeast-1
aws events disable-rule --name claude-news-analyzer-monthly --region ap-northeast-1

# 2. S3からデータをローカルにコピー（必要に応じて）
aws s3 sync s3://claude-news-analyzer/daily/ ./responses/daily/
aws s3 sync s3://claude-news-analyzer/weekly/ ./responses/weekly/
aws s3 sync s3://claude-news-analyzer/monthly/ ./responses/monthly/
aws s3 sync s3://claude-news-analyzer/responses/ ./responses/legacy/

# 3. ローカル環境で手動実行してテスト
export S3_BUCKET_NAME="claude-news-analyzer"
python lambda_handler.py
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

問題が発生した場合は、以下を確認してください。

1. CloudWatch Logs でエラーメッセージを確認
2. Lambda 関数の環境変数が正しく設定されているか確認
3. IAM ロールの権限が `daily/weekly/monthly` に対応しているか確認
4. S3 バケットに `config/config.json` と 3 種類のプロンプトが存在するか確認
5. 週次・月次の場合、入力となる前段レポートが S3 に存在するか確認
