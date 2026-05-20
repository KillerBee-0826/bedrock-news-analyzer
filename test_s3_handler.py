import unittest
from unittest.mock import Mock, patch

import s3_handler
from s3_handler import S3Handler


class S3HandlerSaveTests(unittest.TestCase):
    def _build_handler(self):
        s3_client = Mock()
        fake_boto3 = Mock()
        fake_boto3.client.return_value = s3_client
        with patch.object(s3_handler, "boto3", fake_boto3):
            handler = S3Handler("bucket")
        return handler, s3_client

    def test_save_text_uses_plain_text_content_type(self):
        handler, s3_client = self._build_handler()

        handler.save_text("daily/report.txt", "本文")

        s3_client.put_object.assert_called_once_with(
            Bucket="bucket",
            Key="daily/report.txt",
            Body="本文".encode("utf-8"),
            ContentType="text/plain; charset=utf-8"
        )

    def test_save_html_uses_html_content_type(self):
        handler, s3_client = self._build_handler()

        handler.save_html("daily/report.html", "<!doctype html>")

        s3_client.put_object.assert_called_once_with(
            Bucket="bucket",
            Key="daily/report.html",
            Body="<!doctype html>".encode("utf-8"),
            ContentType="text/html; charset=utf-8"
        )

    def test_save_markdown_uses_markdown_content_type(self):
        handler, s3_client = self._build_handler()

        handler.save_markdown("daily/report.md", "# 本文")

        s3_client.put_object.assert_called_once_with(
            Bucket="bucket",
            Key="daily/report.md",
            Body="# 本文".encode("utf-8"),
            ContentType="text/markdown; charset=utf-8"
        )


if __name__ == "__main__":
    unittest.main()
