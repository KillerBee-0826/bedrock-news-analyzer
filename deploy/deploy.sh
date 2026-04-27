#!/bin/bash
# Lambda関数デプロイスクリプト
# Lambda Layer + Lambda関数を一括デプロイ

set -e

# デフォルト設定
FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-gemini-news-analyzer}"
LAYER_NAME="${LAMBDA_LAYER_NAME:-gemini-news-analyzer-dependencies}"
RUNTIME="python3.11"
HANDLER="lambda_handler.lambda_handler"
TIMEOUT=900  # 15分
MEMORY=1536  # 1.5GB
REGION="${AWS_REGION:-ap-northeast-1}"
S3_BUCKET="${S3_BUCKET_NAME:-gemini-news-analyzer}"

# IAMロールARN（環境変数または手動設定）
ROLE_ARN="${LAMBDA_ROLE_ARN}"

echo "=" * 80
echo "Lambda関数デプロイを開始します"
echo "=" * 80
echo "関数名: $FUNCTION_NAME"
echo "レイヤー名: $LAYER_NAME"
echo "ランタイム: $RUNTIME"
echo "タイムアウト: ${TIMEOUT}秒"
echo "メモリ: ${MEMORY}MB"
echo "リージョン: $REGION"
echo "S3バケット: $S3_BUCKET"
echo "=" * 80

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

# Lambda Layerが存在しない場合は構築
if [ ! -f "lambda-layer.zip" ]; then
    echo "Lambda Layerが見つかりません。構築します..."
    ./deploy/build_layer.sh
fi

echo ""
echo "=== Lambda Layer デプロイ ==="
# Lambda Layerを公開
echo "Lambda Layerを公開中..."
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name ${LAYER_NAME} \
  --zip-file fileb://lambda-layer.zip \
  --compatible-runtimes ${RUNTIME} \
  --region ${REGION} \
  --query 'LayerVersionArn' \
  --output text)

if [ -z "$LAYER_ARN" ]; then
    echo "❌ Lambda Layerの公開に失敗しました"
    exit 1
fi

echo "✓ Lambda Layer作成完了: ${LAYER_ARN}"

echo ""
echo "=== Lambda関数パッケージ作成 ==="
# 既存のzipファイルを削除
rm -f lambda-function.zip

# 関数コードをzip化
echo "Lambda関数コードをパッケージング中..."
zip -r lambda-function.zip \
  lambda_handler.py \
  s3_handler.py \
  cloudwatch_logger.py \
  llm_fetcher.py \
  bedrock_client.py \
  news_scraper.py \
  -q

function_size=$(du -h lambda-function.zip | cut -f1)
echo "✓ Lambda関数パッケージ作成完了: lambda-function.zip ($function_size)"

echo ""
echo "=== Lambda関数デプロイ ==="

# Lambda関数が存在するか確認
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} 2>/dev/null; then
    echo "Lambda関数が既に存在します。更新します..."

    # コードを更新
    aws lambda update-function-code \
      --function-name ${FUNCTION_NAME} \
      --zip-file fileb://lambda-function.zip \
      --region ${REGION} \
      --no-cli-pager > /dev/null

    echo "✓ Lambda関数コード更新完了"

    # 設定を更新
    aws lambda update-function-configuration \
      --function-name ${FUNCTION_NAME} \
      --runtime ${RUNTIME} \
      --handler ${HANDLER} \
      --timeout ${TIMEOUT} \
      --memory-size ${MEMORY} \
      --layers ${LAYER_ARN} \
      --environment "Variables={S3_BUCKET_NAME=${S3_BUCKET}}" \
      --region ${REGION} \
      --no-cli-pager > /dev/null

    echo "✓ Lambda関数設定更新完了"

else
    echo "Lambda関数を新規作成します..."

    # IAMロールARNのチェック
    if [ -z "$ROLE_ARN" ]; then
        echo "❌ エラー: LAMBDA_ROLE_ARN 環境変数が設定されていません"
        echo ""
        echo "IAMロールARNを設定してください:"
        echo "  export LAMBDA_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role"
        echo ""
        echo "または、AWS Management ConsoleでIAMロールを作成し、ARNを取得してください"
        exit 1
    fi

    # Lambda関数を作成
    aws lambda create-function \
      --function-name ${FUNCTION_NAME} \
      --runtime ${RUNTIME} \
      --role ${ROLE_ARN} \
      --handler ${HANDLER} \
      --timeout ${TIMEOUT} \
      --memory-size ${MEMORY} \
      --layers ${LAYER_ARN} \
      --zip-file fileb://lambda-function.zip \
      --environment "Variables={S3_BUCKET_NAME=${S3_BUCKET}}" \
      --region ${REGION} \
      --no-cli-pager > /dev/null

    echo "✓ Lambda関数作成完了"
fi

echo ""
echo "=== デプロイ完了 ==="
echo "✓ Lambda関数名: ${FUNCTION_NAME}"
echo "✓ Lambda Layer ARN: ${LAYER_ARN}"
echo "✓ リージョン: ${REGION}"
echo ""
echo "次のステップ:"
echo "  1. Lambda環境変数を設定:"
echo "     aws lambda update-function-configuration \\"
echo "       --function-name ${FUNCTION_NAME} \\"
echo "       --environment \"Variables={S3_BUCKET_NAME=${S3_BUCKET},GEMINI_API_KEY=YOUR_API_KEY}\" \\"
echo "       --region ${REGION}"
echo ""
echo "  2. S3バケットに設定ファイルをアップロード:"
echo "     aws s3 cp config.json s3://${S3_BUCKET}/config/config.json"
echo "     aws s3 cp news_analysis_prompt.txt s3://${S3_BUCKET}/config/news_analysis_prompt.txt"
echo ""
echo "  3. Lambda関数をテスト実行:"
echo "     aws lambda invoke \\"
echo "       --function-name ${FUNCTION_NAME} \\"
echo "       --region ${REGION} \\"
echo "       output.json"
echo ""
echo "  4. EventBridgeスケジュールを設定（毎日0:00 UTC = 9:00 JST）:"
echo "     aws events put-rule \\"
echo "       --name gemini-news-analyzer-daily \\"
echo "       --schedule-expression 'cron(0 0 * * ? *)' \\"
echo "       --region ${REGION}"
echo ""
echo "     aws events put-targets \\"
echo "       --rule gemini-news-analyzer-daily \\"
echo "       --targets \"Id=1,Arn=arn:aws:lambda:${REGION}:YOUR_ACCOUNT_ID:function:${FUNCTION_NAME}\" \\"
echo "       --region ${REGION}"
