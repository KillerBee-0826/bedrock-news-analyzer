# CLAUDE.md

このファイルは、このリポジトリで作業する際にClaude Code (claude.ai/code) にガイダンスを提供します。

## プロジェクト概要

日本の主要技術メディア（@IT、ITmedia系、クラウドWatch等）から記事を自動収集し、完全な記事本文を取得して、Google Gemini APIで深い分析レポートを生成するシステム。macOS/Linux上でcronを使って毎日自動実行するように設計されています。

**言語**: Python 3.9+（推奨: 3.10+）  
**主要ドキュメント**: README.md（日本語）  
**主要機能**: 
- RSSフィードからのニュース収集（6サイト）
- trafilaturaによる記事本文の高精度抽出（85%以上の成功率）
- Shift_JIS等の日本語エンコーディング自動対応
- 並列処理による高速化（5並列、約3秒で32記事取得）
- Gemini APIによる深掘りトレンド分析

## 開発コマンド

### セットアップ
```bash
# 依存パッケージをインストール
pip3 install -r requirements.txt

# APIキーを設定
cp .env.example .env
# .envを編集してGEMINI_API_KEYを追加
```

### テスト実行
```bash
# 手動テスト実行（約3-5分で完了）
python3 gemini_fetcher.py

# ログを確認
tail -f logs/gemini_fetcher.log    # アプリケーションログ（成功率、文字数統計を表示）
tail -f logs/cron.log               # cron実行ログ

# 今日の結果を表示
cat responses/$(date +%Y-%m-%d)_articles.txt  # 記事一覧（メタデータ + 本文）
cat responses/$(date +%Y-%m-%d).txt           # Gemini分析レポート

# 記事本文取得の統計情報を確認
grep "記事本文取得完了" logs/gemini_fetcher.log | tail -1
```

**期待される出力例**:
```
記事本文取得完了:
  総数: 32件
  成功: 32件 (100.0%)
  失敗: 0件
  平均文字数: 1530文字
  最大文字数: 3981文字
  最小文字数: 383文字
```

### cron設定
```bash
# crontabを編集
crontab -e

# 例: 毎日朝9:00に実行
# 0 9 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 gemini_fetcher.py >> logs/cron.log 2>&1

# cron設定を確認
crontab -l
```

## アーキテクチャ

### コア設計
2ファイル構成のPythonアプリケーション。

**gemini_fetcher.py** - メイン実行ファイル（318行）
- `GeminiFetcher`: Gemini API統合、ニュース分析フロー制御
- `_analyze_news()`: ニュース収集 → 記事本文取得 → Gemini分析の統合フロー (152-174行)
- `fetch_response()`: 指数バックオフによるリトライロジックでGemini APIにクエリ
- `save_response()`: 結果を`responses/`に保存

**news_scraper.py** - ニュース収集・記事本文取得モジュール（650行以上）
- `NewsScraper`: RSS取得、記事本文抽出、並列処理
- `scrape_all_sites()`: 全サイトから並列でRSS取得（68-102行）
- `enrich_articles_with_content()`: 記事本文を並列取得、統計情報収集（380-440行）
- `_fetch_article_content()`: 3段階フォールバック戦略（445-480行）
  1. trafilatura汎用抽出
  2. サイト特化セレクタ
  3. BeautifulSoup汎用フォールバック
- `_decode_response()`: chardetによるShift_JIS等の自動検出（510-565行）
- `format_articles_for_gemini()`: 記事本文を含むフォーマット（620-650行）

### 設定システム
2層の設定構造:
1. **config.json**: ニュース収集設定、記事本文取得設定、サイト別セレクタ、Geminiモデル選択
   - `news_scraping.enabled`: ニュース収集のON/OFF
   - `content_fetching.enabled`: 記事本文取得のON/OFF
   - `content_fetching.parallel_content_workers`: 並列処理数（デフォルト: 5）
   - `sites[].content_selectors`: サイト別のCSSセレクタ
   - `sites[].encoding_fix`: エンコーディング自動検出（"chardet"）
2. **.env**: APIキーのみ（gitで除外）

スクリプトは`Path(__file__).parent.absolute()`と`os.chdir()`を使用して、cronから実行された際にパスが正しく動作することを保証しています。

### エラーハンドリング
- **リトライロジック**: 
  - Gemini API: デフォルトで3回試行、指数バックオフ（5秒、10秒、20秒）
  - HTTP取得: requestsのRetryアダプター（3回、バックオフ係数0.3）
  - 記事本文取得: 3段階フォールバック戦略
- **記事ごとの独立したエラーハンドリング**: 1記事の失敗が他に影響しない
- **二重ログ**: ファイル（logs/gemini_fetcher.log）とコンソール出力の両方
- **統計情報**: 成功率、平均文字数、最大/最小文字数をログ出力
- **終了コード**: 成功時は0、失敗時は1を返す（cron監視用）

### ファイル構造
```
gemini_fetcher.py    # メイン実行ファイル（318行）
news_scraper.py      # ニュース収集・記事本文取得（650行以上）
config.json          # ニュース収集設定、サイト別セレクタ
.env                 # APIキー（gitで除外）
responses/           # 出力:
  ├── YYYY-MM-DD_articles.txt  # 記事一覧（メタデータ + 本文）
  └── YYYY-MM-DD.txt           # Gemini分析レポート
logs/                # gemini_fetcher.log + cron.log
```

## 動作の変更方法

**収集対象サイトを変更**: `config.json` → `"news_scraping.sites"`配列を編集  
**記事本文取得を無効化**: `config.json` → `"content_fetching.enabled": false`（メタデータのみ）  
**並列処理数を変更**: `config.json` → `"parallel_content_workers"`を編集（デフォルト: 5）  
**記事数を制限**: `config.json` → `"max_articles_per_site"`を編集（デフォルト: 30）  
**モデルを変更**: `config.json` → `"gemini_model"`を編集（現在: "gemini-2.5-flash"）  
**リトライ動作を変更**: `config.json` → `"max_retries"`と`"retry_delay"`を編集  
**実行スケジュールを変更**: crontabエントリを編集

## 重要事項

- スクリプトは`responses/`と`logs/`ディレクトリが存在しない場合、自動的に作成します
- cronから実行する場合、絶対パスが重要です（Pythonバイナリとプロジェクトディレクトリの両方）
- 記事一覧ファイル（`_articles.txt`）には、メタデータ + 記事本文（【本文】セクション）が含まれます
- 分析レポートファイル（`.txt`）には、Geminiによる深掘り分析が含まれます
- `.env`ファイルには有効なGEMINI_API_KEYが必要です（Google AI Studioから取得）
- 記事本文取得は3段階フォールバック戦略（trafilatura → サイト特化 → 汎用）で高い成功率を実現
- ITmedia系サイトはShift_JISエンコーディングを使用（chardetで自動検出・対応）
- 実行時間: 約3-5分（RSS取得1分 + 記事本文取得2-3分 + Gemini分析1分）
