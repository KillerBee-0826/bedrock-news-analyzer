import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import email_notifier
from email_notifier import EmailNotifier


class FakeBoto3:
    def __init__(self, secret_string=None, secret_error=None):
        self.secret_string = secret_string
        self.secret_error = secret_error
        self.clients = {}
        self.client_calls = []

    def client(self, service_name, **kwargs):
        self.client_calls.append((service_name, kwargs))
        if service_name == "sesv2":
            client = Mock()
            self.clients["sesv2"] = client
            return client
        if service_name == "secretsmanager":
            client = Mock()
            if self.secret_error:
                client.get_secret_value.side_effect = self.secret_error
            else:
                client.get_secret_value.return_value = {"SecretString": self.secret_string}
            self.clients["secretsmanager"] = client
            return client
        if service_name == "s3":
            client = Mock()
            client.generate_presigned_url.return_value = "https://signed-by-secret.example.com"
            self.clients["s3"] = client
            return client
        raise AssertionError(f"unexpected service: {service_name}")


class EmailNotifierPresignedUrlTests(unittest.TestCase):
    def _build_notifier(self, config, fake_boto3):
        s3_handler = SimpleNamespace(
            bucket_name="bucket",
            s3_client=Mock()
        )
        s3_handler.s3_client.generate_presigned_url.return_value = "https://signed-by-role.example.com"
        boto3_patcher = patch.object(email_notifier, "boto3", fake_boto3)
        config_patcher = patch.object(email_notifier, "Config", lambda **kwargs: kwargs)
        boto3_patcher.start()
        config_patcher.start()
        self.addCleanup(boto3_patcher.stop)
        self.addCleanup(config_patcher.stop)
        notifier = EmailNotifier(config=config, s3_handler=s3_handler)
        return notifier, s3_handler

    def test_iam_user_secret_signer_uses_dedicated_s3_client(self):
        secret = json.dumps({
            "aws_access_key_id": "AKIAEXAMPLE",
            "aws_secret_access_key": "secret"
        })
        fake_boto3 = FakeBoto3(secret_string=secret)
        notifier, s3_handler = self._build_notifier({
            "presigned_url_signer_type": "iam_user_secret",
            "presigned_url_signing_secret_id": "secret-id",
            "presigned_url_signing_secret_region": "ap-northeast-1",
            "presigned_url_s3_region": "ap-northeast-1"
        }, fake_boto3)

        url = notifier._generate_presigned_url("daily/result.txt", 604800)

        self.assertEqual(url, "https://signed-by-secret.example.com")
        self.assertFalse(s3_handler.s3_client.generate_presigned_url.called)
        fake_boto3.clients["secretsmanager"].get_secret_value.assert_called_once_with(
            SecretId="secret-id"
        )
        fake_boto3.clients["s3"].generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "daily/result.txt"},
            ExpiresIn=604800
        )

    def test_iam_user_secret_signer_rejects_session_token(self):
        secret = json.dumps({
            "aws_access_key_id": "AKIAEXAMPLE",
            "aws_secret_access_key": "secret",
            "aws_session_token": "temporary"
        })
        fake_boto3 = FakeBoto3(secret_string=secret)
        notifier, s3_handler = self._build_notifier({
            "presigned_url_signer_type": "iam_user_secret"
        }, fake_boto3)

        with self.assertRaisesRegex(ValueError, "aws_session_token"):
            notifier._generate_presigned_url("daily/result.txt", 604800)

        self.assertFalse(s3_handler.s3_client.generate_presigned_url.called)

    def test_iam_user_secret_signer_does_not_fallback_when_secret_fetch_fails(self):
        fake_boto3 = FakeBoto3(secret_error=RuntimeError("boom"))
        notifier, s3_handler = self._build_notifier({
            "presigned_url_signer_type": "iam_user_secret"
        }, fake_boto3)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            notifier._generate_presigned_url("daily/result.txt", 604800)

        self.assertFalse(s3_handler.s3_client.generate_presigned_url.called)

    def test_default_signer_uses_existing_s3_client(self):
        fake_boto3 = FakeBoto3()
        notifier, s3_handler = self._build_notifier({}, fake_boto3)

        url = notifier._generate_presigned_url("daily/result.txt", 86400)

        self.assertEqual(url, "https://signed-by-role.example.com")
        s3_handler.s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "daily/result.txt"},
            ExpiresIn=86400
        )
        self.assertNotIn("secretsmanager", fake_boto3.clients)

    def test_presigned_url_expiration_must_not_exceed_seven_days(self):
        fake_boto3 = FakeBoto3()
        notifier, s3_handler = self._build_notifier({}, fake_boto3)

        with self.assertRaisesRegex(ValueError, "604800"):
            notifier._generate_presigned_url("daily/result.txt", 604801)

        self.assertFalse(s3_handler.s3_client.generate_presigned_url.called)

    def test_daily_notification_links_to_articles_text_and_analysis_html(self):
        fake_boto3 = FakeBoto3()
        notifier, s3_handler = self._build_notifier({}, fake_boto3)
        s3_handler.s3_client.generate_presigned_url.side_effect = [
            "https://example.com/articles.txt",
            "https://example.com/analysis.html",
        ]

        links = notifier._build_artifact_links(
            "daily",
            {
                "articles": ["daily/2026-05-19_articles.txt"],
                "analysis": ["daily/2026-05-19.html"],
            },
            86400
        )

        self.assertEqual(
            links,
            [
                {"text": "収集記事一覧を開く", "url": "https://example.com/articles.txt"},
                {"text": "分析結果を開く", "url": "https://example.com/analysis.html"},
            ]
        )
        self.assertEqual(s3_handler.s3_client.generate_presigned_url.call_count, 2)


if __name__ == "__main__":
    unittest.main()
