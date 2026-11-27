import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "host" / "webapp"))
sys.path.insert(0, str(ROOT / "core"))

from llm.provider_client import GeminiClient, LLMProviderError
from settings.llm_config import LLMConfigStore


class TestGeminiClient(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = LLMConfigStore(self.temp_dir.name)

        self.store.save_provider("google", {
            "api_key": "test-api-key",
            "model": "gemini-test-model",
        })
        self.store.set_active_provider("google")

        self.response = Mock()
        self.response.read.return_value = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": "Test response"}]
                }
            }]
        }).encode("utf-8")
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)

        self.urlopen = Mock(return_value=self.response)
        self.client = GeminiClient(
            config_store=self.store,
            urlopen_func=self.urlopen,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_sends_correct_request(self):
        result = self.client.generate("Hello Gemini")

        self.assertEqual(result, "Test response")

        request = self.urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-test-model:generateContent",
        )
        self.assertEqual(
            request.get_header("X-goog-api-key"),
            "test-api-key",
        )

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            payload["contents"][0]["parts"][0]["text"],
            "Hello Gemini",
        )

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(LLMProviderError):
            self.client.generate("")

        self.urlopen.assert_not_called()

    def test_inactive_provider_is_rejected(self):
        self.store.set_active_provider("google")
        self.store.save_provider("self-hosted", {
            "base_url": "http://localhost:11434/v1",
            "model": "local-model",
        })
        self.store.set_active_provider("self-hosted")

        with self.assertRaises(LLMProviderError):
            self.client.generate("Hello")

        self.urlopen.assert_not_called()

    def test_invalid_response_is_rejected(self):
        self.response.read.return_value = b'{}'

        with self.assertRaises(LLMProviderError):
            self.client.generate("Hello")

    def test_http_error_is_handled(self):
        from urllib.error import HTTPError

        self.urlopen.side_effect = HTTPError(
            url="https://example.com",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

        with self.assertRaisesRegex(
            LLMProviderError,
            "HTTP 429",
        ):
            self.client.generate("Hello")

    def test_connection_error_is_handled(self):
        from urllib.error import URLError

        self.urlopen.side_effect = URLError("Connection failed")

        with self.assertRaisesRegex(
            LLMProviderError,
            "Could not connect",
        ):
            self.client.generate("Hello")



if __name__ == "__main__":
    unittest.main()
