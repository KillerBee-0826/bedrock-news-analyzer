import json
import sys
import types
import unittest
from datetime import timezone
from unittest.mock import Mock, patch

if "boto3" not in sys.modules:
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = Mock()
    sys.modules["boto3"] = boto3_stub

if "botocore" not in sys.modules:
    botocore_stub = types.ModuleType("botocore")
    botocore_config_stub = types.ModuleType("botocore.config")
    botocore_exceptions_stub = types.ModuleType("botocore.exceptions")

    class ClientError(Exception):
        pass

    class Config:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    botocore_config_stub.Config = Config
    botocore_exceptions_stub.ClientError = ClientError
    sys.modules["botocore"] = botocore_stub
    sys.modules["botocore.config"] = botocore_config_stub
    sys.modules["botocore.exceptions"] = botocore_exceptions_stub

if "pytz" not in sys.modules:
    pytz_stub = types.ModuleType("pytz")
    pytz_stub.timezone = Mock(return_value=timezone.utc)
    sys.modules["pytz"] = pytz_stub

import lambda_handler


class LambdaHandlerErrorResponseTests(unittest.TestCase):
    def test_unhandled_exception_response_hides_internal_details_and_logs_traceback(self):
        logger = Mock()
        secret_message = "Sensitive AWS detail: arn:aws:s3:::private-bucket"

        with patch.dict(lambda_handler.os.environ, {"S3_BUCKET_NAME": "private-bucket"}, clear=True):
            with patch.object(lambda_handler, "setup_cloudwatch_logger", return_value=logger):
                with patch.object(lambda_handler, "S3Handler", side_effect=RuntimeError(secret_message)):
                    response = lambda_handler.lambda_handler({"analysis_type": "daily"}, Mock())

        self.assertEqual(response["statusCode"], 500)

        body = json.loads(response["body"])
        self.assertEqual(
            body,
            {
                "success": False,
                "error": "Lambda関数実行中にエラーが発生しました",
            },
        )

        response_body = response["body"]
        self.assertNotIn("traceback", body)
        self.assertNotIn(secret_message, response_body)
        self.assertNotIn("RuntimeError", response_body)
        self.assertNotIn("Traceback", response_body)

        error_logs = [call.args[0] for call in logger.error.call_args_list]
        self.assertTrue(any(secret_message in message for message in error_logs))
        self.assertTrue(any("Traceback (most recent call last)" in message for message in error_logs))
        self.assertTrue(any("RuntimeError" in message for message in error_logs))


if __name__ == "__main__":
    unittest.main()
