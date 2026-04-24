#!/usr/bin/env python3
"""
Gemini自動質問取得スクリプト
毎日指定の時間にGemini APIに質問を送信し、回答を保存します。
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path

try:
    import google.generativeai as genai
    from dotenv import load_dotenv
except ImportError as e:
    print(f"必要なパッケージがインストールされていません: {e}")
    print("以下のコマンドを実行してください: pip3 install -r requirements.txt")
    sys.exit(1)


class GeminiFetcher:
    """Gemini APIを使用して質問の回答を取得するクラス"""

    def __init__(self, config_path: str = "config.json"):
        """
        初期化

        Args:
            config_path: 設定ファイルのパス
        """
        # プロジェクトルートディレクトリに移動
        self.script_dir = Path(__file__).parent.absolute()
        os.chdir(self.script_dir)

        # 環境変数の読み込み
        load_dotenv()

        # 設定ファイルの読み込み
        self.config = self._load_config(config_path)

        # ログの設定
        self._setup_logging()

        # APIキーの設定
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            self.logger.error("GEMINI_API_KEYが設定されていません")
            raise ValueError("GEMINI_API_KEY環境変数を設定してください")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.config["gemini_model"])

        # プロンプトテンプレートの読み込み
        prompt_path = self.config.get("news_analysis_prompt_path", "news_analysis_prompt.txt")
        self.prompt_template = self._load_prompt_template(prompt_path)

        self.logger.info("GeminiFetcherを初期化しました")

    def _load_config(self, config_path: str) -> dict:
        """
        設定ファイルを読み込む

        Args:
            config_path: 設定ファイルのパス

        Returns:
            設定の辞書
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            print(f"設定ファイルが見つかりません: {config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"設定ファイルのJSON形式が不正です: {e}")
            sys.exit(1)

    def _load_prompt_template(self, template_path: str) -> str:
        """
        プロンプトテンプレートファイルを読み込む

        Args:
            template_path: プロンプトテンプレートファイルのパス（相対パスまたは絶対パス）

        Returns:
            プロンプトテンプレート文字列
        """
        try:
            if not Path(template_path).is_absolute():
                template_path = self.script_dir / template_path

            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()

            if not template.strip():
                self.logger.error(f"プロンプトテンプレートファイルが空です: {template_path}")
                print(f"エラー: プロンプトテンプレートファイルが空です: {template_path}")
                sys.exit(1)

            self.logger.info(f"プロンプトテンプレートを読み込みました: {template_path}")
            return template

        except FileNotFoundError:
            self.logger.error(f"プロンプトテンプレートファイルが見つかりません: {template_path}")
            print(f"エラー: プロンプトテンプレートファイルが見つかりません: {template_path}")
            print(f"news_analysis_prompt.txt ファイルをプロジェクトルート ({self.script_dir}) に配置してください")
            sys.exit(1)
        except UnicodeDecodeError as e:
            self.logger.error(f"プロンプトテンプレートファイルのエンコーディングエラー: {e}")
            print(f"エラー: プロンプトテンプレートファイルはUTF-8エンコーディングで保存してください")
            sys.exit(1)
        except Exception as e:
            self.logger.error(f"プロンプトテンプレートの読み込みに失敗しました: {str(e)}")
            print(f"エラー: プロンプトテンプレートの読み込みに失敗しました: {str(e)}")
            sys.exit(1)

    def _setup_logging(self):
        """ログの設定"""
        logs_dir = Path(self.config["logs_dir"])
        logs_dir.mkdir(exist_ok=True)

        log_file = logs_dir / "gemini_fetcher.log"

        # ロガーの設定
        self.logger = logging.getLogger("GeminiFetcher")
        self.logger.setLevel(logging.INFO)

        # ファイルハンドラ
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # コンソールハンドラ
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # フォーマッター
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def fetch_response(self, question: str) -> str:
        """
        Gemini APIに質問を送信し、回答を取得する（リトライ機能付き）

        Args:
            question: Geminiに送信する質問

        Returns:
            Geminiからの回答テキスト

        Raises:
            Exception: 最大リトライ回数を超えても失敗した場合
        """
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay"]

        for attempt in range(max_retries):
            try:
                self.logger.info(f"質問を送信中 (試行 {attempt + 1}/{max_retries})")
                response = self.model.generate_content(question)

                if not response.text:
                    raise ValueError("Geminiからの回答が空です")

                self.logger.info(
                    f"回答を取得しました (文字数: {len(response.text)})"
                )
                return response.text

            except Exception as e:
                self.logger.warning(
                    f"試行 {attempt + 1}/{max_retries} 失敗: {str(e)}"
                )

                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    self.logger.info(f"{wait_time}秒待機してリトライします")
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"最大リトライ回数({max_retries})に達しました"
                    )
                    raise

    def _analyze_news(self) -> str:
        """
        ニュース分析を実行

        Returns:
            Geminiによる分析結果
        """
        from news_scraper import NewsScraper

        scraper = NewsScraper(self.config, self.logger)
        articles_by_site = scraper.scrape_all_sites()

        # 記事本文を取得（新規追加）
        articles_by_site = scraper.enrich_articles_with_content(articles_by_site)

        # 記事をフォーマット
        formatted = scraper.format_articles_for_gemini(articles_by_site)

        # フォーマットされた記事をファイルに保存
        self._save_formatted_articles(formatted)

        # 分析プロンプトを生成
        prompt = self._create_news_analysis_prompt(formatted)

        # Gemini APIで分析
        return self.fetch_response(prompt)

    def _save_formatted_articles(self, formatted_articles: str):
        """
        フォーマットされた記事をファイルに保存

        Args:
            formatted_articles: フォーマットされた記事テキスト
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        responses_dir = Path(self.config["responses_dir"])
        responses_dir.mkdir(exist_ok=True)

        output_file = responses_dir / f"{date_str}_articles.txt"

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(formatted_articles)

            self.logger.info(f"記事一覧をファイルに保存しました: {output_file}")
        except Exception as e:
            self.logger.error(f"記事一覧の保存に失敗しました: {str(e)}")

    def _create_news_analysis_prompt(self, formatted_articles: str) -> str:
        """
        ニュース分析用のプロンプトを生成

        Args:
            formatted_articles: フォーマットされた記事テキスト

        Returns:
            分析プロンプト
        """
        try:
            return self.prompt_template.format(formatted_articles=formatted_articles)
        except KeyError as e:
            self.logger.error(f"プロンプトテンプレートの変数置換エラー: {e}")
            self.logger.error("テンプレートに {formatted_articles} プレースホルダーが必要です")
            print("エラー: プロンプトテンプレートの形式が不正です")
            sys.exit(1)

    def save_response(self, response: str, date_str: str = None, section: str = "question"):
        """
        回答をファイルに保存する

        Args:
            response: 保存する回答テキスト
            date_str: 日付文字列（省略時は今日の日付）
            section: セクション名（"question" or "news_analysis"）
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        responses_dir = Path(self.config["responses_dir"])
        responses_dir.mkdir(exist_ok=True)

        output_file = responses_dir / f"{date_str}.txt"

        try:
            # 既存ファイルがあれば追記モード、なければ新規作成
            mode = "a" if output_file.exists() else "w"

            with open(output_file, mode, encoding="utf-8") as f:
                if mode == "a":
                    f.write("\n\n" + "=" * 80 + "\n\n")

                if section == "news_analysis":
                    f.write(f"# ニュース分析レポート\n")
                    f.write(f"日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("-" * 80 + "\n\n")
                    f.write(response)
                else:
                    f.write(f"質問: {self.config['question']}\n")
                    f.write(f"日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("-" * 80 + "\n\n")
                    f.write(response)

            self.logger.info(f"回答をファイルに保存しました: {output_file}")
        except Exception as e:
            self.logger.error(f"ファイル保存に失敗しました: {str(e)}")
            raise

    def run(self):
        """メイン処理を実行"""
        try:
            self.logger.info("=" * 80)
            self.logger.info("処理を開始します")

            # ニュース分析処理
            if self.config.get('news_scraping', {}).get('enabled', False):
                self.logger.info("ニュース分析を開始")
                news_response = self._analyze_news()
                self.save_response(news_response, section="news_analysis")

            # 既存の質問処理（オプション）
            question = self.config.get("question", "")
            if question and question != "ここに毎日Geminiに投げたい質問を入力してください":
                self.logger.info(f"質問を処理: {question}")
                response = self.fetch_response(question)
                self.save_response(response, section="question")

            self.logger.info("処理が正常に完了しました")
            self.logger.info("=" * 80)
            return True

        except Exception as e:
            self.logger.error(f"処理中にエラーが発生しました: {str(e)}", exc_info=True)
            self.logger.info("=" * 80)
            return False


def main():
    """メイン関数"""
    try:
        fetcher = GeminiFetcher()
        success = fetcher.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"致命的なエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
