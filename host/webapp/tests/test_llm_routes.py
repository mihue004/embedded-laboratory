import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent / "core"))

from settings.llm_config import LLMConfigError, LLMConfigStore
from settings.llm_routes import llm_bp


class TestLLMRoutes(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = LLMConfigStore(self.temp_dir.name)

        app = Flask(__name__)
        app.register_blueprint(
            llm_bp,
            url_prefix="/settings/llm",
        )
        self.client = app.test_client()

        self.store_patch = patch(
            "settings.llm_routes.get_llm_store",
            return_value=self.store,
        )
        self.store_patch.start()

    def tearDown(self):
        self.store_patch.stop()
        self.temp_dir.cleanup()

    def test_get_config_initializes_files(self):
        response = self.client.get("/settings/llm/config")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json["active_provider"])
        self.assertEqual(response.json["providers"], {})
        self.assertTrue(self.store.config_path.is_file())
        self.assertTrue(self.store.key_path.is_file())

    def test_save_openai_provider(self):
        response = self.client.post(
            "/settings/llm/providers/openai",
            json={
                "api_key": "test-api-key",
                "model": "test-model",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.json["providers"]["openai"]["configured"]
        )
        self.assertTrue(
            response.json["providers"]["openai"]["api_key_configured"]
        )
        self.assertNotIn("test-api-key", response.get_data(as_text=True))

    def test_activate_provider(self):
        self.store.save_provider(
            "openai",
            {
                "api_key": "test-api-key",
                "model": "test-model",
            },
        )

        response = self.client.post(
            "/settings/llm/active",
            json={"provider_id": "openai"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["active_provider"], "openai")

    def test_unconfigured_provider_cannot_be_activated(self):
        response = self.client.post(
            "/settings/llm/active",
            json={"provider_id": "openai"},
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_json_body_is_rejected(self):
        response = self.client.post(
            "/settings/llm/providers/openai",
            json=[],
        )

        self.assertEqual(response.status_code, 400)

    @patch("settings.llm_routes.GeminiClient")
    def test_gemini_test_success(self, mock_client):
        self.store.save_provider("google", {
            "api_key": "test-api-key",
            "model": "test-model",
        })
        self.store.set_active_provider("google")

        mock_client.return_value.generate.return_value = "Test response"

        response = self.client.post(
            "/settings/llm/test",
            json={"prompt": "Hello Gemini"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["response"], "Test response")
        mock_client.return_value.generate.assert_called_once_with(
            "Hello Gemini"
        )

    def test_gemini_test_rejects_empty_prompt(self):
        response = self.client.post(
            "/settings/llm/test",
            json={"prompt": "  "},
        )

        self.assertEqual(response.status_code, 400)

    def test_gemini_test_rejects_inactive_provider(self):
        response = self.client.post(
            "/settings/llm/test",
            json={"prompt": "Hello Gemini"},
        )

        self.assertEqual(response.status_code, 400)

    @patch("settings.llm_routes.GeminiClient")
    def test_gemini_provider_error_is_handled(self, mock_client):
        from llm.provider_client import LLMProviderError

        self.store.save_provider("google", {
            "api_key": "test-api-key",
            "model": "test-model",
        })
        self.store.set_active_provider("google")

        mock_client.return_value.generate.side_effect = (
            LLMProviderError("Could not connect to Google Gemini.")
        )

        response = self.client.post(
            "/settings/llm/test",
            json={"prompt": "Hello Gemini"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Could not connect", response.json["error"])

    def test_gemini_test_rejects_invalid_json(self):
        response = self.client.post(
            "/settings/llm/test",
            data="invalid json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_gemini_test_rejects_missing_prompt(self):
        response = self.client.post(
            "/settings/llm/test",
            json={},
        )

        self.assertEqual(response.status_code, 400)

    @patch(
        "settings.llm_routes.get_llm_store",
        side_effect=LLMConfigError("Configuration unavailable."),
    )
    def test_gemini_test_handles_config_error(self, mock_store):
        response = self.client.post(
            "/settings/llm/test",
            json={"prompt": "Hello Gemini"},
        )

        self.assertEqual(response.status_code, 500)
        self.assertIn("Configuration unavailable", response.json["error"])

if __name__ == "__main__":
    unittest.main()