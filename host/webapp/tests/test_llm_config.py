import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from settings.llm_config import LLMConfigError, LLMConfigStore


class TestLLMConfigStore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = LLMConfigStore(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_config_returns_defaults(self):
        config = self.store.get_config()

        self.assertIsNone(config["active_provider"])
        self.assertEqual(config["providers"], {})
        self.assertEqual(config["generation"]["temperature"], 0.7)

    def test_save_openai_provider(self):
        config = self.store.save_provider("openai", {
            "api_key": "test-secret",
            "model": "test-model",
        })

        self.assertTrue(config["providers"]["openai"]["configured"])
        self.assertTrue(
            config["providers"]["openai"]["api_key_configured"]
        )
        self.assertNotIn(
            "api_key",
            config["providers"]["openai"],
        )

    def test_api_key_is_encrypted_at_rest(self):
        secret = "my-test-api-key"

        self.store.save_provider("openai", {
            "api_key": secret,
            "model": "test-model",
        })

        stored_data = self.store.config_path.read_text()

        self.assertNotIn(secret, stored_data)
        self.assertEqual(
            self.store.get_api_key("openai"),
            secret,
        )

    def test_multiple_providers_are_preserved(self):
        self.store.save_provider("openai", {
            "api_key": "openai-secret",
            "model": "model-a",
        })

        self.store.save_provider("anthropic", {
            "api_key": "anthropic-secret",
            "model": "model-b",
        })

        config = self.store.get_config()

        self.assertIn("openai", config["providers"])
        self.assertIn("anthropic", config["providers"])
        self.assertEqual(
            config["providers"]["openai"]["model"],
            "model-a",
        )
        self.assertEqual(
            config["providers"]["anthropic"]["model"],
            "model-b",
        )

    def test_active_provider_can_be_changed(self):
        self.store.save_provider("openai", {
            "api_key": "secret-a",
            "model": "model-a",
        })
        self.store.save_provider("anthropic", {
            "api_key": "secret-b",
            "model": "model-b",
        })

        self.store.set_active_provider("anthropic")

        self.assertEqual(
            self.store.get_config()["active_provider"],
            "anthropic",
        )

    def test_unconfigured_provider_cannot_be_activated(self):
        with self.assertRaises(LLMConfigError):
            self.store.set_active_provider("openai")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(LLMConfigError):
            self.store.save_provider("unknown", {
                "api_key": "secret",
                "model": "model",
            })

    def test_existing_api_key_is_preserved(self):
        self.store.save_provider("openai", {
            "api_key": "original-secret",
            "model": "model-a",
        })

        self.store.save_provider("openai", {
            "api_key": "",
            "model": "model-b",
        })

        self.assertEqual(
            self.store.get_api_key("openai"),
            "original-secret",
        )

    def test_config_and_key_have_restricted_permissions(self):
        self.store.save_provider("openai", {
            "api_key": "secret",
            "model": "model-a",
        })

        config_mode = stat.S_IMODE(
            self.store.config_path.stat().st_mode
        )
        key_mode = stat.S_IMODE(
            self.store.key_path.stat().st_mode
        )

        self.assertEqual(config_mode, 0o600)
        self.assertEqual(key_mode, 0o600)

    def test_self_hosted_provider_without_api_key(self):
        config = self.store.save_provider("self-hosted", {
            "base_url": "http://localhost:11434/v1",
            "model": "local-model",
        })

        self.assertTrue(
            config["providers"]["self-hosted"]["configured"]
        )
        self.assertIsNone(self.store.get_api_key("self-hosted"))


if __name__ == "__main__":
    unittest.main()