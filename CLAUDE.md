# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

日本の主要技術メディア（@IT、ITmedia系、クラウドWatch等）から記事を自動収集し、Amazon Bedrock (Claude)で深い分析レポートを生成するシステム。AWS LambdaとローカルmacOS/Linux環境の両方で動作します。

**言語**: Python 3.9+（推奨: 3.11+）  
**LLMプロバイダー**: Amazon Bedrock (Claude Sonnet 4.5)  
**主要ドキュメント**: README.md（日本語）、LAMBDA_DEPLOYMENT.md（AWS Lambda デプロイ手順）

**主要機能**: 
- RSSフィードからのニュース収集（6サイト）
- trafilaturaによる記事本文の高精度抽出（85%以上の成功率）
- Shift_JIS等の日本語エンコーディング自動対応
- 並列処理による高速化（5並列、約3秒で32記事取得）
- Amazon Bedrock (Claude)による深掘りトレンド分析

## 開発コマンド

### セットアップ
```bash
# 依存パッケージをインストール
pip3 install -r requirements.txt

# AWS認証情報を設定（ローカル環境）
aws configure
# または ~/.aws/credentials を手動設定
```

### ローカル実行
```bash
# 手動テスト実行（約3-5分で完了）
python3 llm_fetcher.py

# ログを確認
tail -f logs/news_analyzer.log

# 今日の結果を表示
cat responses/$(date +%Y-%m-%d)_articles.txt  # 記事一覧（メタデータ + 本文）
cat responses/$(date +%Y-%m-%d).txt           # Claude分析レポート

# 記事本文取得の統計情報を確認
grep "記事本文取得完了" logs/news_analyzer.log | tail -1
```

### Lambda デプロイ
```bash
# Lambda Layer構築（依存パッケージ）
./deploy/build_layer.sh

# Lambda関数デプロイ
export LAMBDA_ROLE_ARN="arn:aws:iam::ACCOUNT_ID:role/lambda-claude-news-analyzer"
export S3_BUCKET_NAME="claude-news-analyzer"
./deploy/deploy.sh

# 設定ファイルをS3にアップロード
aws s3 cp config/config.json s3://claude-news-analyzer/config/config.json
aws s3 cp config/news_analysis_prompt.txt s3://claude-news-analyzer/config/news_analysis_prompt.txt

# Lambda関数をテスト実行
aws lambda invoke --function-name claude-news-analyzer output.json
cat output.json
```

詳細は `LAMBDA_DEPLOYMENT.md` を参照してください。

### cron設定（ローカル環境）
```bash
# crontabを編集
crontab -e

# 例: 毎日朝9:00に実行
# 0 9 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 llm_fetcher.py >> logs/cron.log 2>&1

# cron設定を確認
crontab -l
```

## アーキテクチャ

### デュアル環境対応
システムはLambda環境とローカル環境の両方で動作するように設計されています。

**Lambda環境**:
- エントリーポイント: `lambda_handler.py`
- S3から設定とプロンプトを読み込み
- CloudWatch Logsにログ出力
- EventBridgeスケジュール（毎日0:00 UTC = 9:00 JST）

**ローカル環境**:
- エントリーポイント: `llm_fetcher.py` （直接実行）
- ローカルファイルシステムから設定を読み込み
- ファイルにログ出力（`logs/news_analyzer.log`）

### コアモジュール

**llm_fetcher.py** - LLM統合・メインフロー（約480行）
- `LLMFetcher.__init__()`: Lambda用初期化（S3からパラメータ受け取り）
- `LLMFetcher.__init_local__()`: ローカル用初期化（ファイルシステムから読み込み）
- `_analyze_news()`: ニュース収集 → 記事本文取得 → Claude分析の統合フロー
- `fetch_response()`: 指数バックオフによるリトライロジック
- `save_response()`: S3またはローカルファイルシステムに保存

**bedrock_client.py** - Amazon Bedrock (Claude) クライアント（約150行）
- `BedrockClient.generate_content()`: Bedrock APIへのリクエスト送信
- Anthropic Messages API形式でリクエスト構築
- トークン使用量の追跡とログ記録
- IAM認証（APIキー不要）

**news_scraper.py** - ニュース収集・記事本文取得（約765行）
- `NewsScraper.scrape_all_sites()`: 全サイトから並列でRSS取得
- `enrich_articles_with_content()`: 記事本文を並列取得、統計情報収集
- `_fetch_article_content()`: 3段階フォールバック戦略
  1. trafilatura汎用抽出
  2. サイト特化CSSセレクタ
  3. BeautifulSoup汎用フォールバック
- `_decode_response()`: chardetによるShift_JIS等の自動検出
- `format_articles_for_llm()`: LLM用に記事をフォーマット（本文含む）

**lambda_handler.py** - Lambda関数エントリーポイント（約155行）
- EventBridge Schedulerからのイベント受信
- S3から動的に設定とプロンプトを読み込み
- `LLMFetcher`を初期化して実行
- CloudWatch Logsへの自動ロギング

**s3_handler.py** - S3操作ヘルパー（約180行）
- `load_json()`, `load_text()`: S3からの読み込み
- `save_text()`: S3への書き込み
- `object_exists()`: オブジェクト存在確認

**cloudwatch_logger.py** - Lambda環境用ロギング設定（約70行）
- CloudWatch Logs用のログフォーマッター
- Lambda実行コンテキスト情報の自動付与

### 設定システム

**階層構造**:
```
config/
├── config.json                  # メイン設定（LLM、ニュース収集）
└── news_analysis_prompt.txt     # Claude用プロンプトテンプレート
```

**config.json の主要設定**:
- `llm_provider`: "bedrock"（固定）
- `bedrock_model`: "us.anthropic.claude-sonnet-4-6"
- `bedrock_region`: "us-east-1"
- `bedrock_max_tokens`: 4096
- `news_scraping.enabled`: ニュース収集のON/OFF
- `content_fetching.enabled`: 記事本文取得のON/OFF
- `content_fetching.parallel_content_workers`: 並列処理数（デフォルト: 5）
- `sites[].content_selectors`: サイト別のCSSセレクタ
- `sites[].encoding_fix`: "chardet"（ITmedia対策）

### パス管理の重要ポイント

**ローカル環境**:
- `llm_fetcher.py`は`Path(__file__).parent.absolute()`で作業ディレクトリを決定
- `os.chdir()`でプロジェクトルートに移動（cron実行時のパス問題対策）
- 設定ファイルはプロジェクトルートからの相対パス（`config/config.json`）

**Lambda環境**:
- S3キーパス: `config/config.json`, `config/news_analysis_prompt.txt`
- 出力: `responses/YYYY-MM-DD.txt`, `responses/YYYY-MM-DD_articles.txt`
- Lambda関数zipは直下に全Pythonファイルを配置（サブディレクトリなし）

### エラーハンドリング
- **リトライロジック**: 
  - Bedrock API: デフォルトで3回試行、指数バックオフ（5秒、10秒、20秒）
  - HTTP取得: requestsのRetryアダプター（3回、バックオフ係数0.3）
  - 記事本文取得: 3段階フォールバック戦略
- **記事ごとの独立したエラーハンドリング**: 1記事の失敗が他に影響しない
- **二重ログ**: ファイル/CloudWatch Logs + コンソール出力
- **統計情報**: 成功率、平均文字数、最大/最小文字数をログ出力
- **終了コード**: 成功時は0、失敗時は1を返す（cron監視用）

### ディレクトリ構造
```
autoLLMGetter/
├── config/
│   ├── config.json                  # メイン設定
│   └── news_analysis_prompt.txt     # Claudeプロンプト
├── deploy/
│   ├── build_layer.sh               # Lambda Layer構築スクリプト
│   ├── deploy.sh                    # Lambda関数デプロイスクリプト
│   ├── Dockerfile.layer             # Lambda Layer Docker定義
│   └── policies/                    # IAMポリシー
│       ├── trust-policy.json
│       └── permissions-policy.json
├── llm_fetcher.py                   # メイン実行ファイル（ローカル）
├── lambda_handler.py                # Lambda関数エントリーポイント
├── bedrock_client.py                # Bedrock API クライアント
├── news_scraper.py                  # ニュース収集・記事本文取得
├── s3_handler.py                    # S3操作ヘルパー
├── cloudwatch_logger.py             # CloudWatch Logs設定
├── requirements.txt                 # ローカル開発用依存関係
├── requirements-lambda.txt          # Lambda Layer用依存関係
├── .env.example                     # 環境変数テンプレート（非使用）
├── responses/                       # ローカル実行時の出力（.gitignore）
└── logs/                            # ローカルログ（.gitignore）
```

**注意**: `.env`ファイルは現在使用していません。ローカル環境はAWS CLIの認証情報（`~/.aws/credentials`）を使用します。

## 動作の変更方法

**収集対象サイトを変更**: `config/config.json` → `"news_scraping.sites"`配列を編集  
**記事本文取得を無効化**: `config/config.json` → `"content_fetching.enabled": false`  
**並列処理数を変更**: `config/config.json` → `"parallel_content_workers"`を編集（デフォルト: 5）  
**記事数を制限**: `config/config.json` → `"max_articles_per_site"`を編集（デフォルト: 30）  
**Claudeモデルを変更**: `config/config.json` → `"bedrock_model"`を編集  
**リトライ動作を変更**: `config/config.json` → `"max_retries"`と`"retry_delay"`を編集  
**実行スケジュールを変更**: EventBridgeルール（Lambda）またはcrontabエントリ（ローカル）を編集  
**プロンプトをカスタマイズ**: `config/news_analysis_prompt.txt`を編集

## 重要事項

### 認証
- **ローカル環境**: AWS CLIの認証情報（`~/.aws/credentials`または環境変数）が必要
- **Lambda環境**: IAMロール経由で自動認証（APIキー不要）
- IAMユーザー/ロールには`bedrock:InvokeModel`権限が必要

### パス
- ローカル実行: プロジェクトルートから相対パス（`config/config.json`）
- Lambda実行: S3キーパス（`config/config.json`）
- cronから実行する場合、絶対パスを使用（Pythonバイナリとプロジェクトディレクトリ）

### ファイル
- 記事一覧ファイル（`_articles.txt`）: メタデータ + 記事本文（【本文】セクション）
- 分析レポートファイル（`.txt`）: Claudeによる深掘り分析
- ログファイル: `logs/news_analyzer.log`（ローカル）、CloudWatch Logs（Lambda）
- `responses/`と`logs/`ディレクトリは自動作成

### パフォーマンス
- 実行時間: 約3-5分（RSS取得1分 + 記事本文取得2-3分 + Claude分析1分）
- 記事本文取得: 3段階フォールバック戦略で85%以上の成功率
- ITmedia系サイト: Shift_JISエンコーディングをchardetで自動検出

### Lambda制限
- タイムアウト: 15分（設定済み）
- メモリ: 1.5GB（推奨）
- Lambda Layer: 50MB制限（zipファイルサイズ）
- トークン使用量はCloudWatch Logsに記録
