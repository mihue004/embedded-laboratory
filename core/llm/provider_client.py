
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
)


class LLMProviderError(Exception):
    """Raised when an LLM provider request fails."""


class GeminiClient:
    """Client for Google's Gemini GenerateContent REST API."""

    def __init__(self, config_store=None, urlopen_func=None):
        self.config_store = config_store
        self.urlopen = urlopen_func or urlopen

    def generate(self, prompt):
        if not isinstance(prompt, str) or not prompt.strip():
            raise LLMProviderError("A non-empty prompt is required.")

        if self.config_store is None:
            raise LLMProviderError("No LLM configuration store available.")

        config = self.config_store.get_config()

        if config.get("active_provider") != "google":
            raise LLMProviderError("Google Gemini is not the active provider.")

        provider = config["providers"].get("google", {})
        model = provider.get("model")
        api_key = self.config_store.get_api_key("google")

        if not model or not api_key:
            raise LLMProviderError("Google Gemini is not fully configured.")

        generation = config.get("generation", {})
        timeout = generation.get("timeout", 120)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": generation.get("temperature", 0.7),
                "maxOutputTokens": generation.get("max_tokens", 4096),
            },
        }

        url = f"{GEMINI_API_URL}{quote(model, safe='')}:generateContent"

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )

        try:
            with self.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))

        except HTTPError as exc:
            raise LLMProviderError(
                f"Google Gemini returned HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise LLMProviderError(
                f"Could not connect to Google Gemini: {reason}"
            ) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise LLMProviderError(
                "Google Gemini returned an invalid response."
            ) from exc

        try:
            parts = result["candidates"][0]["content"]["parts"]
            text = "".join(
                part["text"]
                for part in parts
                if isinstance(part.get("text"), str)
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "Google Gemini returned no usable text."
            ) from exc

        if not text.strip():
            raise LLMProviderError("Google Gemini returned an empty response.")

        return text
