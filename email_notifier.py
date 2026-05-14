#!/usr/bin/env python3
"""
Amazon SESによる分析完了メール通知
S3上の非公開オブジェクトを期限付きURLで共有する。
"""

import logging
from datetime import datetime
from html import escape
from typing import Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


class EmailNotifier:
    """Amazon SESを使って分析結果の通知メールを送信するクラス"""

    def __init__(
        self,
        config: dict,
        s3_handler,
        logger: Optional[logging.Logger] = None
    ):
        """
        初期化

        Args:
            config: email_notification設定
            s3_handler: S3Handlerインスタンス
            logger: ロガー
        """
        if boto3 is None:
            raise ImportError("boto3がインストールされていません。Lambda環境では必須です。")

        self.config = config
        self.s3_handler = s3_handler
        self.logger = logger or logging.getLogger("EmailNotifier")
        self.ses_client = boto3.client("sesv2", region_name=self.config.get("ses_region", "ap-northeast-1"))

    def send_analysis_notification(
        self,
        analysis_type: str,
        artifacts: Dict[str, List[str]],
        executed_at: datetime
    ) -> None:
        """
        分析完了通知を送信する

        Args:
            analysis_type: 分析種別（daily, weekly, monthly）
            artifacts: 通知対象のS3キー一覧
            executed_at: 実行日時
        """
        sender = self.config.get("sender")
        recipients = self.config.get("recipients", [])
        if not sender or not recipients:
            raise ValueError("email_notification.sender と recipients を設定してください")

        expires_seconds = int(self.config.get("presigned_url_expires_seconds", 86400))
        subject = self._build_subject(analysis_type, executed_at)
        text_body, html_body = self._build_body(analysis_type, artifacts, executed_at, expires_seconds)

        self.logger.info(
            f"SESメール通知を送信します: analysis_type={analysis_type}, recipients={len(recipients)}"
        )
        self.ses_client.send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": recipients},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"}
                    }
                }
            }
        )
        self.logger.info("SESメール通知を送信しました")

    def _build_subject(self, analysis_type: str, executed_at: datetime) -> str:
        analysis_label = self._analysis_label(analysis_type)
        date_text = executed_at.strftime("%Y-%m-%d")
        return f"{analysis_label}完了通知 - {date_text}"

    def _build_body(
        self,
        analysis_type: str,
        artifacts: Dict[str, List[str]],
        executed_at: datetime,
        expires_seconds: int
    ) -> tuple[str, str]:
        analysis_label = self._analysis_label(analysis_type)
        expires_hours = expires_seconds / 3600
        links = self._build_artifact_links(analysis_type, artifacts, expires_seconds)

        text_lines = [
            f"{analysis_label}が完了しました。",
            "",
            f"分析種別: {analysis_type}",
            f"実行日時: {executed_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"URL有効期限: {expires_seconds}秒（約{expires_hours:.1f}時間）",
            "",
            "生成ファイル:"
        ]

        for link in links:
            text_lines.append(f"- {link['url']}")

        text_lines.extend([
            "",
            "このURLを知っている人は有効期限内にファイルへアクセスできます。",
            "不要な転送や公開場所への貼り付けは避けてください。"
        ])
        text_body = "\n".join(text_lines)

        link_items = "\n".join(
            f'<li><a href="{escape(link["url"], quote=True)}">{escape(link["text"])}</a></li>'
            for link in links
        )
        html_body = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>{escape(analysis_label)}完了通知</title>
</head>
<body>
  <p>{escape(analysis_label)}が完了しました。</p>
  <dl>
    <dt>分析種別</dt>
    <dd>{escape(analysis_type)}</dd>
    <dt>実行日時</dt>
    <dd>{escape(executed_at.strftime('%Y-%m-%d %H:%M:%S %Z'))}</dd>
    <dt>URL有効期限</dt>
    <dd>{expires_seconds}秒（約{expires_hours:.1f}時間）</dd>
  </dl>
  <p>生成ファイル:</p>
  <ul>
{link_items}
  </ul>
  <p>このURLを知っている人は有効期限内にファイルへアクセスできます。不要な転送や公開場所への貼り付けは避けてください。</p>
</body>
</html>"""
        return text_body, html_body

    def _build_artifact_links(
        self,
        analysis_type: str,
        artifacts: Dict[str, List[str]],
        expires_seconds: int
    ) -> List[Dict[str, str]]:
        links = []
        target_labels = ["articles", "analysis"] if analysis_type == "daily" else ["analysis"]
        for label in target_labels:
            for key in artifacts.get(label, []):
                links.append({
                    "text": self._artifact_link_text(label),
                    "url": self._generate_presigned_url(key, expires_seconds)
                })
        return links

    def _generate_presigned_url(self, key: str, expires_seconds: int) -> str:
        try:
            return self.s3_handler.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.s3_handler.bucket_name, "Key": key},
                ExpiresIn=expires_seconds
            )
        except ClientError as e:
            self.logger.error(f"presigned URL生成に失敗しました: key={key}, error={e}")
            raise

    def _analysis_label(self, analysis_type: str) -> str:
        labels = {
            "daily": "日次ニュース分析",
            "weekly": "週次ニュース分析",
            "monthly": "月次ニュース分析"
        }
        return labels.get(analysis_type, analysis_type)

    def _artifact_label(self, label: str) -> str:
        labels = {
            "articles": "収集記事一覧",
            "analysis": "分析結果"
        }
        return labels.get(label, label)

    def _artifact_link_text(self, label: str) -> str:
        return f"{self._artifact_label(label)}を開く"
