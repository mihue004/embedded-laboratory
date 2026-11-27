
import json
import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


DEFAULT_CONFIG_DIR = Path("/var/lib/embedded-lab")

PROVIDER_IDS = {"openai", "anthropic", "google", "self-hosted"}

PROVIDER_FIELDS = {
    "model",
    "base_url",
    "organization_id",
    "api_format",
}


class LLMConfigError(Exception):
    """Base exception for LLM configuration errors."""


class LLMConfigStore:
    """Manages encrypted LLM provider configuration."""

    def __init__(self, config_dir=None):
        self.config_dir = Path(
            config_dir or os.environ.get(
                "EMBEDDED_LAB_CONFIG_DIR",
                DEFAULT_CONFIG_DIR,
            )
        )
        self.config_path = self.config_dir / "llm-providers.json"
        self.key_path = self.config_dir / "llm.key"

    def _ensure_directory(self):
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def initialize(self):
        """Create the configuration directory and initial files if needed."""
        self._ensure_directory()
        self._get_fernet()

        if not self.config_path.exists():
            self._save(self._default_config())

    def _get_fernet(self):
        self._ensure_directory()

        try:
            key = self.key_path.read_bytes()
        except FileNotFoundError:
            key = Fernet.generate_key()
            try:
                fd = os.open(
                    self.key_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                with os.fdopen(fd, "wb") as handle:
                    handle.write(key)
            except FileExistsError:
                key = self.key_path.read_bytes()

        return Fernet(key)

    def _default_config(self):
        return {
            "version": 1,
            "active_provider": None,
            "providers": {},
            "generation": {
                "temperature": 0.7,
                "max_tokens": 4096,
                "timeout": 120,
            },
        }

    def _load(self):
        if not self.config_path.exists():
            return self._default_config()

        try:
            data = json.loads(
                self.config_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise LLMConfigError(
                "The LLM configuration could not be read."
            ) from exc

        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or not isinstance(data.get("providers"), dict)
        ):
            raise LLMConfigError(
                "The LLM configuration has an invalid structure."
            )

        return data

    def _save(self, data):
        self._ensure_directory()
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.config_dir,
                prefix=".llm-config-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(data, handle, indent=2)
                handle.write("\n")

            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.config_path)
            os.chmod(self.config_path, 0o600)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    def _is_configured(self, provider_id, provider):
        if not isinstance(provider, dict) or not provider.get("model"):
            return False

        if provider_id in {"openai", "anthropic", "google"}:
            return bool(provider.get("encrypted_api_key"))

        if provider_id == "self-hosted":
            return bool(provider.get("base_url"))

        return False

    def get_config(self):
        self.initialize()
        data = self._load()
        providers = {}

        for provider_id, provider in data["providers"].items():
            if not isinstance(provider, dict):
                continue

            public_data = {
                key: value
                for key, value in provider.items()
                if key != "encrypted_api_key"
            }
            public_data["api_key_configured"] = bool(
                provider.get("encrypted_api_key")
            )
            public_data["configured"] = self._is_configured(
                provider_id, provider
            )
            providers[provider_id] = public_data

        return {
            "version": data["version"],
            "active_provider": data.get("active_provider"),
            "providers": providers,
            "generation": data.get(
                "generation",
                self._default_config()["generation"],
            ),
        }

    def save_provider(self, provider_id, settings):
        if provider_id not in PROVIDER_IDS:
            raise LLMConfigError("Unknown provider.")

        if not isinstance(settings, dict):
            raise LLMConfigError("Provider settings must be an object.")

        data = self._load()
        existing = data["providers"].get(provider_id, {})

        provider = {
            key: value
            for key, value in existing.items()
            if key == "encrypted_api_key"
        }

        for key in PROVIDER_FIELDS:
            if key in settings:
                value = settings[key]
                if not isinstance(value, str):
                    raise LLMConfigError(
                        f"Invalid provider setting: {key}"
                    )
                provider[key] = value.strip()

        api_key = settings.get("api_key", "")
        if api_key is not None and not isinstance(api_key, str):
            raise LLMConfigError("Invalid API key.")

        if api_key:
            provider["encrypted_api_key"] = (
                self._get_fernet()
                .encrypt(api_key.encode("utf-8"))
                .decode("ascii")
            )

        if not provider.get("model"):
            raise LLMConfigError("A model must be specified.")

        if provider_id in {"openai", "anthropic", "google"}:
            if not provider.get("encrypted_api_key"):
                raise LLMConfigError("An API key is required.")

        if provider_id == "self-hosted" and not provider.get("base_url"):
            raise LLMConfigError("An API endpoint is required.")

        data["providers"][provider_id] = provider
        self._save(data)
        return self.get_config()

    def set_active_provider(self, provider_id):
        data = self._load()
        provider = data["providers"].get(provider_id)

        if not self._is_configured(provider_id, provider):
            raise LLMConfigError(
                "The selected provider is not configured."
            )

        data["active_provider"] = provider_id
        self._save(data)
        return self.get_config()

    def get_api_key(self, provider_id):
        data = self._load()
        provider = data["providers"].get(provider_id, {})
        encrypted_key = provider.get("encrypted_api_key")

        if not encrypted_key:
            return None

        try:
            return self._get_fernet().decrypt(
                encrypted_key.encode("ascii")
            ).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise LLMConfigError(
                "The stored API key cannot be decrypted."
            ) from exc
