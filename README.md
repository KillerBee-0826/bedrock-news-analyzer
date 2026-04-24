# Gemini自動ニュース分析システム

毎日指定の時間に日本の主要技術メディアから記事を収集し、完全な記事本文を取得して、Google Gemini APIで深い分析レポートを自動生成するシステムです。

## 主要機能

### ニュース収集・分析
- **6つの主要技術メディアから自動収集**: @IT、ITmedia エンタープライズ、ITmedia AI+、クラウドWatch、AI Watch、日経クロステック
- **RSSフィードからメタデータ取得**: タイトル、URL、概要、発行日時
- **記事本文の完全取得**: trafilaturaを使用した高精度な本文抽出（85%以上の成功率）
- **エンコーディング自動対応**: Shift_JIS等の日本語エンコーディングを自動検出
- **並列処理**: 5並列で高速処理（約3秒で32記事取得）

### Gemini AI分析
- 記事本文に基づく深掘りトレンド分析
- 注目ニュースの詳細分析（200-300文字）
- 技術分野の自動分類（AI/機械学習、セキュリティ、クラウド等）
- ビジネスインパクト分析

### システム機能
- 3回までの自動リトライ（指数バックオフ）
- 詳細なログ記録（成功率、文字数統計）
- エラー時も処理継続（記事ごとの独立したエラーハンドリング）
- 簡単な設定ファイルでカスタマイズ可能

## 必要要件

- Python 3.9以上（推奨: 3.10+）
- Google Gemini APIキー
- macOS / Linux（cronを使用）

## セットアップ手順

### 1. 依存パッケージのインストール

```bash
pip3 install -r requirements.txt
```

### 2. APIキーの設定

`.env.example`をコピーして`.env`ファイルを作成し、APIキーを設定します：

```bash
cp .env.example .env
```

`.env`ファイルを編集してAPIキーを設定：

```
GEMINI_API_KEY=あなたのAPIキーをここに入力
```

**APIキーの取得方法**:
1. [Google AI Studio](https://makersuite.google.com/app/apikey)にアクセス
2. 「Create API Key」をクリック
3. APIキーをコピーして`.env`ファイルに貼り付け

### 3. ニュース収集の設定

`config.json`ファイルで、ニュース収集と記事本文取得の設定を確認・カスタマイズできます：

```json
{
  "question": "",
  "gemini_model": "gemini-2.5-flash",
  "max_retries": 3,
  "retry_delay": 5,
  "responses_dir": "responses",
  "logs_dir": "logs",
  
  "news_scraping": {
    "enabled": true,
    "scrape_yesterday_articles": true,
    "timezone": "Asia/Tokyo",
    "timeout_per_site": 30,
    "parallel_workers": 3,
    "max_articles_per_site": 30,
    "user_agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
    
    "content_fetching": {
      "enabled": true,
      "timeout_per_article": 10,
      "parallel_content_workers": 5,
      "max_content_length": 50000,
      "min_content_length": 200
    },
    
    "sites": [
      {
        "name": "@IT",
        "rss_url": "https://rss.itmedia.co.jp/rss/2.0/ait.xml",
        "encoding_fix": "chardet",
        "content_selectors": {
          "article": [".article-body", "article", "main"],
          "remove": [".ad", ".related", ".sns-share", "nav", "footer"]
        }
      }
      // ... 他5サイト
    ]
  }
}
```

**主要設定項目**:
- `news_scraping.enabled`: ニュース収集機能のON/OFF
- `content_fetching.enabled`: 記事本文取得のON/OFF（falseでメタデータのみ）
- `max_articles_per_site`: サイトごとの最大記事数（デフォルト: 30）
- `parallel_content_workers`: 記事本文取得の並列処理数（デフォルト: 5）

### 4. 動作テスト

手動で実行して動作を確認します：

```bash
python3 gemini_fetcher.py
```

成功すると、`responses/`ディレクトリに2つのファイルが作成されます：
- `YYYY-MM-DD_articles.txt`: 収集した記事一覧（メタデータ + 本文）
- `YYYY-MM-DD.txt`: Geminiによる分析レポート

**実行例**:
```
2026-04-23 14:12:10 - INFO - スクレイピング開始: 6サイトを3並列で処理
2026-04-23 14:12:13 - INFO - スクレイピング完了: 合計32記事取得
2026-04-23 14:12:13 - INFO - 記事本文取得開始: 32件を5並列で処理
2026-04-23 14:12:16 - INFO - 記事本文取得完了:
2026-04-23 14:12:16 - INFO -   総数: 32件
2026-04-23 14:12:16 - INFO -   成功: 32件 (100.0%)
2026-04-23 14:12:16 - INFO -   失敗: 0件
2026-04-23 14:12:16 - INFO -   平均文字数: 1530文字
```

### 5. cron設定（自動実行）

毎日朝9:00に自動実行するには、crontabを設定します。

#### crontabの編集

```bash
crontab -e
```

#### エントリの追加

以下の行を追加します（パスは環境に合わせて変更してください）：

```bash
0 9 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 gemini_fetcher.py >> logs/cron.log 2>&1
```

**重要なポイント**:
- `cd /Users/queenbee/git/autoLLMGetter` の部分は、実際のプロジェクトパスに変更してください
- `/usr/bin/python3` は `which python3` コマンドで確認したPythonのパスを使用してください

#### cron設定の確認

```bash
crontab -l
```

#### テスト実行

次の分に実行するように一時的に設定してテストすることをお勧めします：

```bash
# 例: 現在時刻が10:30の場合、10:31に実行
31 10 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 gemini_fetcher.py >> logs/cron.log 2>&1
```

実行後、以下を確認：
- `logs/cron.log` にcronからの出力があるか
- `logs/gemini_fetcher.log` に実行ログがあるか
- `responses/` に今日の日付のファイルが作成されているか

問題なければ、実際の実行時刻（9:00）に変更してください。

## ディレクトリ構造

```
autoLLMGetter/
├── gemini_fetcher.py       # メインスクリプト
├── news_scraper.py         # ニュース収集・記事本文取得モジュール
├── config.json             # 設定ファイル
├── .env                    # APIキー（gitignore対象）
├── .env.example            # 環境変数サンプル
├── requirements.txt        # Python依存パッケージ
├── .gitignore              # Git除外設定
├── CLAUDE.md               # Claude Code向けプロジェクトドキュメント
├── responses/              # 出力ファイル
│   ├── 2026-04-23_articles.txt  # 記事一覧（メタデータ + 本文）
│   └── 2026-04-23.txt           # Gemini分析レポート
├── logs/                   # ログファイル
│   ├── gemini_fetcher.log  # 実行ログ
│   └── cron.log            # cronの出力ログ
└── README.md               # このファイル
```

## 使い方

### 収集対象サイトの変更

`config.json`の`news_scraping.sites`配列を編集して、収集するサイトを追加・削除できます：

```json
{
  "news_scraping": {
    "sites": [
      {
        "name": "新しいサイト",
        "rss_url": "https://example.com/rss.xml",
        "encoding_fix": "chardet",  // 必要な場合のみ
        "content_selectors": {
          "article": [".article", "article", "main"],
          "remove": [".ad", "nav", "footer"]
        }
      }
    ]
  }
}
```

### 記事本文取得の無効化

記事本文取得が不要な場合（メタデータのみで十分な場合）は、無効化できます：

```json
{
  "news_scraping": {
    "content_fetching": {
      "enabled": false
    }
  }
}
```

これにより、実行時間が短縮され（約1分）、RSSの概要のみでGemini分析が行われます。

### ログの確認

実行ログを確認：

```bash
tail -f logs/gemini_fetcher.log
```

cronのログを確認：

```bash
tail -f logs/cron.log
```

### 結果の確認

```bash
# 今日の記事一覧を表示（メタデータ + 本文）
cat responses/$(date +%Y-%m-%d)_articles.txt

# 今日の分析レポートを表示
cat responses/$(date +%Y-%m-%d).txt

# 全ての結果を一覧
ls -lt responses/

# 記事本文取得の統計情報を確認
grep "記事本文取得完了" logs/gemini_fetcher.log | tail -5
```

## トラブルシューティング

### 記事本文取得の成功率が低い場合

1. **ログで詳細を確認**:
   ```bash
   grep "記事本文取得" logs/gemini_fetcher.log | tail -20
   ```

2. **タイムアウト時間を延長**:
   `config.json`で調整：
   ```json
   {
     "news_scraping": {
       "content_fetching": {
         "timeout_per_article": 15,
         "parallel_content_workers": 3
       }
     }
   }
   ```

3. **特定サイトのセレクタを調整**:
   記事本文が取得できないサイトの`content_selectors`を修正

### エンコーディング文字化けが発生する場合

1. **該当サイトにchardetを有効化**:
   ```json
   {
     "name": "サイト名",
     "encoding_fix": "chardet"
   }
   ```

2. **ログでエンコーディング検出結果を確認**:
   ```bash
   grep "エンコーディング" logs/gemini_fetcher.log
   ```

### cronが実行されない場合

1. **cronが動作しているか確認**:
   ```bash
   ps aux | grep cron
   ```

2. **パスを絶対パスに変更**:
   - `which python3` でPythonのフルパスを確認
   - プロジェクトディレクトリも絶対パスで指定

3. **ログファイルを確認**:
   ```bash
   cat logs/cron.log
   cat logs/gemini_fetcher.log
   ```

### APIエラーが発生する場合

1. **APIキーを確認**:
   ```bash
   cat .env
   ```

2. **APIキーが有効か確認**:
   - [Google AI Studio](https://makersuite.google.com/app/apikey)で確認

3. **ログでエラー詳細を確認**:
   ```bash
   grep ERROR logs/gemini_fetcher.log
   ```

### 回答が保存されない場合

1. **ディレクトリの権限を確認**:
   ```bash
   ls -ld responses logs
   ```

2. **手動実行でテスト**:
   ```bash
   python3 gemini_fetcher.py
   ```

## カスタマイズ

### 実行時刻の変更

crontabのエントリを編集します：

```bash
# 毎日21:00に実行
0 21 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 gemini_fetcher.py >> logs/cron.log 2>&1

# 毎日7:00と19:00に実行（1日2回）
0 7,19 * * * cd /Users/queenbee/git/autoLLMGetter && /usr/bin/python3 gemini_fetcher.py >> logs/cron.log 2>&1
```

### パフォーマンスチューニング

より高速に処理したい場合：

```json
{
  "news_scraping": {
    "parallel_workers": 5,  // RSS取得の並列数を増やす（デフォルト: 3）
    "max_articles_per_site": 20,  // 記事数を減らす（デフォルト: 30）
    "content_fetching": {
      "parallel_content_workers": 8,  // 本文取得の並列数を増やす（デフォルト: 5）
      "timeout_per_article": 5  // タイムアウトを短くする（デフォルト: 10）
    }
  }
}
```

**注意**: 並列数を増やしすぎると、サイト側でアクセス制限される可能性があります。

### リトライ回数の変更

`config.json`で設定を変更：

```json
{
  "max_retries": 5,
  "retry_delay": 10
}
```

### 分析プロンプトのカスタマイズ

`news_analysis_prompt.txt`を編集することで、Geminiへの分析指示を自由にカスタマイズできます：

```
# news_analysis_prompt.txt を直接編集
# Pythonの知識なしで分析の観点や形式を変更可能
```

**重要事項**:
- `{formatted_articles}` プレースホルダーは必須（記事データの挿入位置）
- UTF-8エンコーディングで保存してください
- `config.json`の`news_analysis_prompt_path`で別のファイルを指定することも可能

### モデルの変更

`config.json`で使用するGeminiモデルを変更：

```json
{
  "gemini_model": "gemini-2.5-flash"
}
```

利用可能なモデル:
- `gemini-2.5-flash`: 高速・低コスト（推奨）
- `gemini-pro`: バランス型
- `gemini-ultra`: 最高品質（利用可能な場合）

## 技術スタック

- **記事本文抽出**: trafilatura (ボイラープレート自動除去)
- **エンコーディング検出**: chardet (Shift_JIS等の日本語対応)
- **HTML解析**: BeautifulSoup4 + lxml
- **RSS解析**: feedparser
- **AI分析**: Google Gemini API (gemini-2.5-flash)
- **並列処理**: ThreadPoolExecutor (5並列)

## アーキテクチャ

### 3段階フォールバック戦略

記事本文抽出は以下の順序で試行されます：

1. **trafilatura汎用抽出** (第一選択、85%成功想定)
   - 広告・ナビゲーション自動除去
   - 複数の記事抽出アルゴリズムを内部で試行

2. **サイト特化セレクタ** (trafilatura失敗時)
   - config.jsonで定義されたCSSセレクタを使用
   - サイトごとに最適化された抽出

3. **BeautifulSoup汎用フォールバック** (最終手段)
   - 汎用セレクタで記事本文を推測
   - 最低限の品質保証

### データフロー

```
RSS取得 (3並列)
  ↓
メタデータ抽出
  ↓
記事本文取得 (5並列) ← 3段階フォールバック
  ↓
フォーマット (記事本文含む)
  ↓
Gemini分析
  ↓
保存 (articles.txt + 分析レポート.txt)
```

## 将来の拡張案

- メール/Slack通知機能
- Web UIでの記事閲覧・検索機能
- より多くの技術メディアへの対応
- 記事の重要度スコアリング
- トレンドキーワードの時系列分析

## ライセンス

このプロジェクトは自由に使用・改変できます。

## 参考リンク

- [Google Gemini API Documentation](https://ai.google.dev/docs)
- [Google AI Studio](https://makersuite.google.com/)
- [cron設定ガイド](https://crontab.guru/)
