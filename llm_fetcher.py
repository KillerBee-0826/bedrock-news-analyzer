#!/usr/bin/env python3
"""
LLM統合スクリプト
AWS Lambda環境とローカル環境で動作し、Amazon Bedrock (Claude)を使用してニュース分析を実行します。
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import boto3
    from bedrock_client import BedrockClient
except ImportError as e:
    print(f"必要なパッケージがインストールされていません: {e}")
    print("Lambda環境ではboto3が組み込まれています")
    sys.exit(1)

# dotenvはローカル開発時のみ使用（Lambda環境では不要）
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


class LLMFetcher:
    """LLM (Bedrock/Gemini) を使用して質問の回答を取得するクラス（Lambda対応版）"""

    def __init__(self, config: dict, prompt_template: str, s3_handler, logger: logging.Logger):
        """
        Lambda用初期化（設定をパラメータで受け取る）

        Args:
            config: 設定辞書（S3から読み込み済み）
            prompt_template: プロンプトテンプレート文字列（S3から読み込み済み）
            s3_handler: S3操作ヘルパー（S3Handlerインスタンス）
            logger: ロガーインスタンス（CloudWatch Logs用）
        """
        self.config = config
        self.prompt_template = prompt_template
        self.s3_handler = s3_handler
        self.logger = logger

        # プロバイダーを決定（bedrock または gemini）
        provider = self.config.get("llm_provider", "bedrock")
        self.logger.info(f"LLMプロバイダー: {provider}")

        if provider == "bedrock":
            # Amazon Bedrock (Claude) を使用
            model_id = self.config.get("bedrock_model", "anthropic.claude-sonnet-4-5-v2:0")
            region = self.config.get("bedrock_region", "us-east-1")
            max_tokens = self.config.get("bedrock_max_tokens", 4096)

            self.model = BedrockClient(
                model_id=model_id,
                region=region,
                logger=self.logger,
                max_tokens=max_tokens
            )
            self.logger.info(f"Bedrockクライアント初期化完了: {model_id}")

        else:
            self.logger.error(f"未サポートのLLMプロバイダー: {provider}")
            self.logger.error("現在はBedrock (Claude)のみサポートしています")
            raise ValueError(f"未サポートのLLMプロバイダー: {provider}. config.jsonでllm_provider='bedrock'を設定してください")

    def __init_local__(self, config_path: str = "config.json"):
        """
        ローカル環境用初期化（互換性のため残す）

        Args:
            config_path: 設定ファイルのパス
        """
        # プロジェクトルートディレクトリに移動
        self.script_dir = Path(__file__).parent.absolute()
        os.chdir(self.script_dir)

        # 環境変数の読み込み
        if load_dotenv:
            load_dotenv()

        # 設定ファイルの読み込み
        self.config = self._load_config(config_path)

        # ログの設定
        self._setup_logging()

        # プロバイダーを決定
        provider = self.config.get("llm_provider", "bedrock")
        self.logger.info(f"LLMプロバイダー: {provider}")

        if provider == "bedrock":
            # Amazon Bedrock (Claude) を使用
            model_id = self.config.get("bedrock_model", "anthropic.claude-sonnet-4-5-v2:0")
            region = self.config.get("bedrock_region", "us-east-1")
            max_tokens = self.config.get("bedrock_max_tokens", 4096)

            self.model = BedrockClient(
                model_id=model_id,
                region=region,
                logger=self.logger,
                max_tokens=max_tokens
            )
            self.logger.info(f"Bedrockクライアント初期化完了: {model_id}")

        else:
            self.logger.error(f"未サポートのLLMプロバイダー: {provider}")
            self.logger.error("現在はBedrock (Claude)のみサポートしています")
            raise ValueError(f"未サポートのLLMプロバイダー: {provider}. config.jsonでllm_provider='bedrock'を設定してください")

        # プロンプトテンプレートの読み込み
        prompt_path = self.config.get("news_analysis_prompt_path", "news_analysis_prompt.txt")
        self.prompt_template = self._load_prompt_template(prompt_path)

        # S3Handlerはローカル環境では不使用
        self.s3_handler = None

        self.logger.info("LLMFetcherを初期化しました（ローカルモード）")

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

        log_file = logs_dir / "news_analyzer.log"

        # ロガーの設定
        self.logger = logging.getLogger("NewsAnalyzer")
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
        LLM (Bedrock/Gemini) に質問を送信し、回答を取得する（リトライ機能付き）

        Args:
            question: LLMに送信する質問

        Returns:
            LLMからの回答テキスト

        Raises:
            Exception: 最大リトライ回数を超えても失敗した場合
        """
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay"]

        for attempt in range(max_retries):
            try:
                self.logger.info(f"質問を送信中 (試行 {attempt + 1}/{max_retries})")

                # generate_content()はBedrock/Gemini両対応
                response_text = self.model.generate_content(question)

                if not response_text:
                    raise ValueError("LLMからの回答が空です")

                self.logger.info(
                    f"回答を取得しました (文字数: {len(response_text)})"
                )

                # トークン使用量をログ（Bedrockの場合のみ）
                if hasattr(self.model, 'get_usage_stats'):
                    usage = self.model.get_usage_stats()
                    self.logger.info(
                        f"Token usage: input={usage.get('input_tokens', 0)}, "
                        f"output={usage.get('output_tokens', 0)}"
                    )

                return response_text

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
            LLM (Bedrock/Gemini) による分析結果
        """
        from news_scraper import NewsScraper

        scraper = NewsScraper(self.config, self.logger)
        articles_by_site = scraper.scrape_all_sites()

        # 記事本文を取得（新規追加）
        articles_by_site = scraper.enrich_articles_with_content(articles_by_site)

        # 記事をフォーマット
        formatted = scraper.format_articles_for_llm(articles_by_site)

        # フォーマットされた記事をファイルに保存
        self._save_formatted_articles(formatted)

        # 分析プロンプトを生成
        prompt = self._create_news_analysis_prompt(formatted)

        # LLMで分析
        return self.fetch_response(prompt)

    def _save_formatted_articles(self, formatted_articles: str) -> str:
        """
        フォーマットされた記事を保存（S3またはローカルファイル）

        Args:
            formatted_articles: フォーマットされた記事テキスト

        Returns:
            保存先パス（S3キーまたはファイルパス）
        """
        date_str = datetime.now().strftime("%Y-%m-%d")

        try:
            # Lambda環境（S3Handler使用）
            if self.s3_handler is not None:
                s3_key = f"responses/{date_str}_articles.txt"
                self.s3_handler.save_text(s3_key, formatted_articles)
                self.logger.info(f"記事一覧をS3に保存しました: s3://{self.s3_handler.bucket_name}/{s3_key}")
                return s3_key

            # ローカル環境（ファイルシステム使用）
            else:
                responses_dir = Path(self.config["responses_dir"])
                responses_dir.mkdir(exist_ok=True)
                output_file = responses_dir / f"{date_str}_articles.txt"

                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(formatted_articles)

                self.logger.info(f"記事一覧をファイルに保存しました: {output_file}")
                return str(output_file)

        except Exception as e:
            self.logger.error(f"記事一覧の保存に失敗しました: {str(e)}")
            raise

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

    def save_response(self, response: str, date_str: Optional[str] = None, section: str = "question") -> str:
        """
        回答を保存（S3またはローカルファイル）

        Args:
            response: 保存する回答テキスト
            date_str: 日付文字列（省略時は今日の日付）
            section: セクション名（"question" or "news_analysis"）

        Returns:
            保存先パス（S3キーまたはファイルパス）
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # レスポンス本文を構築
        content_lines = []
        if section == "news_analysis":
            content_lines.append(f"# ニュース分析レポート")
            content_lines.append(f"日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            content_lines.append("-" * 80)
            content_lines.append("")
            content_lines.append(response)
        else:
            content_lines.append(f"質問: {self.config.get('question', '')}")
            content_lines.append(f"日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            content_lines.append("-" * 80)
            content_lines.append("")
            content_lines.append(response)

        content = "\n".join(content_lines)

        try:
            # Lambda環境（S3Handler使用）
            if self.s3_handler is not None:
                s3_key = f"responses/{date_str}.txt"

                # S3では追記が難しいため、既存ファイルを読み込んで結合
                if self.s3_handler.object_exists(s3_key):
                    existing_content = self.s3_handler.load_text(s3_key)
                    content = existing_content + "\n\n" + "=" * 80 + "\n\n" + content

                self.s3_handler.save_text(s3_key, content)
                self.logger.info(f"LLM分析レポートをS3に保存しました: s3://{self.s3_handler.bucket_name}/{s3_key}")
                return s3_key

            # ローカル環境（ファイルシステム使用）
            else:
                responses_dir = Path(self.config["responses_dir"])
                responses_dir.mkdir(exist_ok=True)
                output_file = responses_dir / f"{date_str}.txt"

                # 既存ファイルがあれば追記モード、なければ新規作成
                mode = "a" if output_file.exists() else "w"

                with open(output_file, mode, encoding="utf-8") as f:
                    if mode == "a":
                        f.write("\n\n" + "=" * 80 + "\n\n")
                    f.write(content)

                self.logger.info(f"回答をファイルに保存しました: {output_file}")
                return str(output_file)

        except Exception as e:
            self.logger.error(f"保存に失敗しました: {str(e)}")
            raise

    def run(self) -> bool:
        """
        メイン処理を実行

        Returns:
            成功時True、失敗時False
        """
        try:
            self.logger.info("=" * 80)
            self.logger.info("News Analyzer (Bedrock Claude) - 処理を開始します")

            # ニュース分析処理
            if self.config.get('news_scraping', {}).get('enabled', False):
                self.logger.info("ニュース分析を開始")
                news_response = self._analyze_news()
                self.save_response(news_response, section="news_analysis")
            else:
                self.logger.warning("ニュース分析が無効化されています（config.news_scraping.enabled = false）")

            # 既存の質問処理（オプション）
            question = self.config.get("question", "")
            if question and question != "ここに毎日Geminiに投げたい質問を入力してください" and question.strip():
                self.logger.info(f"追加質問を処理: {question[:50]}...")
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
    """
    ローカル環境用メイン関数
    Lambda環境では使用しない（lambda_handler.pyを使用）
    """
    try:
        # ローカル環境用の初期化
        fetcher_instance = object.__new__(LLMFetcher)
        fetcher_instance.__init_local__()
        success = fetcher_instance.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"致命的なエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 80)
    print("ローカル環境での実行")
    print("注意: Lambda環境ではlambda_handler.pyを使用してください")
    print("=" * 80)
    print()
    main()
