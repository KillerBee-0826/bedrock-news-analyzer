import logging
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from llm_fetcher import LLMFetcher


class LLMFetcherHtmlOutputTests(unittest.TestCase):
    def _build_fetcher(self):
        fetcher = object.__new__(LLMFetcher)
        fetcher.config = {
            "responses_dir": "responses",
            "output_prefixes": {
                "daily": "daily",
                "weekly": "weekly",
                "monthly": "monthly",
            },
            "news_scraping": {
                "timezone": "Asia/Tokyo",
            },
        }
        fetcher.s3_handler = SimpleNamespace(
            bucket_name="bucket",
            object_exists=Mock(return_value=False),
            load_text=Mock(),
            save_text=Mock(),
            save_markdown=Mock(),
            save_html=Mock(),
            list_objects=Mock(return_value=[]),
        )
        fetcher.logger = logging.getLogger("LLMFetcherHtmlOutputTests")
        return fetcher

    def test_save_response_saves_markdown_and_returns_html_key_for_daily_analysis(self):
        fetcher = self._build_fetcher()

        key = fetcher.save_response(
            "# 見出し\n\n| 列 | 値 |\n| --- | --- |\n| A | 1 |",
            date_str="2026-05-19",
            section="news_analysis"
        )

        self.assertEqual(key, "daily/2026-05-19.html")
        fetcher.s3_handler.save_markdown.assert_called_once()
        self.assertEqual(fetcher.s3_handler.save_markdown.call_args.args[0], "daily/2026-05-19.md")
        fetcher.s3_handler.save_text.assert_not_called()
        fetcher.s3_handler.save_html.assert_called_once()
        self.assertEqual(fetcher.s3_handler.save_html.call_args.args[0], "daily/2026-05-19.html")
        self.assertIn("<table>", fetcher.s3_handler.save_html.call_args.args[1])

    def test_save_periodic_response_saves_markdown_and_returns_html_key(self):
        fetcher = self._build_fetcher()

        key = fetcher.save_periodic_response(
            "週間サマリー",
            "weekly",
            "2026-05-10_2026-05-16",
            "週次ニュース分析レポート"
        )

        self.assertEqual(key, "weekly/2026-05-10_2026-05-16.html")
        fetcher.s3_handler.save_markdown.assert_called_once()
        self.assertEqual(
            fetcher.s3_handler.save_markdown.call_args.args[0],
            "weekly/2026-05-10_2026-05-16.md"
        )
        fetcher.s3_handler.save_text.assert_not_called()
        fetcher.s3_handler.save_html.assert_called_once()
        self.assertEqual(
            fetcher.s3_handler.save_html.call_args.args[0],
            "weekly/2026-05-10_2026-05-16.html"
        )

    def test_load_daily_analysis_prefers_markdown_then_legacy_text(self):
        fetcher = self._build_fetcher()
        existing = {"daily/2026-05-19.md": "md本文"}
        fetcher.s3_handler.object_exists.side_effect = lambda key: key in existing
        fetcher.s3_handler.load_text.side_effect = lambda key: existing[key]

        report = fetcher._load_daily_analysis(date(2026, 5, 18))

        self.assertEqual(report, "## 2026-05-18\n\nmd本文")
        fetcher.s3_handler.object_exists.assert_any_call("daily/2026-05-19.md")
        fetcher.s3_handler.load_text.assert_called_once_with("daily/2026-05-19.md")

    def test_load_daily_analysis_falls_back_to_text(self):
        fetcher = self._build_fetcher()
        existing = {"daily/2026-05-19.txt": "txt本文"}
        fetcher.s3_handler.object_exists.side_effect = lambda key: key in existing
        fetcher.s3_handler.load_text.side_effect = lambda key: existing[key]

        report = fetcher._load_daily_analysis(date(2026, 5, 18))

        self.assertEqual(report, "## 2026-05-18\n\ntxt本文")
        self.assertEqual(
            [call.args[0] for call in fetcher.s3_handler.object_exists.call_args_list],
            [
                "daily/2026-05-19.md",
                "daily/2026-05-19.txt",
            ],
        )

    def test_load_weekly_analyses_for_month_prefers_markdown_without_duplicates(self):
        fetcher = self._build_fetcher()
        fetcher.s3_handler.list_objects.return_value = [
            "weekly/2026-05-03_2026-05-09.txt",
            "weekly/2026-05-10_2026-05-16.txt",
            "weekly/2026-05-10_2026-05-16.md",
        ]
        contents = {
            "weekly/2026-05-03_2026-05-09.txt": "旧週次",
            "weekly/2026-05-10_2026-05-16.txt": "重複txt",
            "weekly/2026-05-10_2026-05-16.md": "新週次",
        }
        fetcher.s3_handler.load_text.side_effect = lambda key: contents[key]

        report = fetcher._load_weekly_analyses_for_month(date(2026, 5, 1), date(2026, 5, 31))

        self.assertIn("旧週次", report)
        self.assertIn("新週次", report)
        self.assertNotIn("重複txt", report)
        self.assertEqual(
            [call.args[0] for call in fetcher.s3_handler.load_text.call_args_list],
            [
                "weekly/2026-05-03_2026-05-09.txt",
                "weekly/2026-05-10_2026-05-16.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
