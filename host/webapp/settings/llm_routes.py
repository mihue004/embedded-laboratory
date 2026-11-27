from flask import Blueprint, jsonify, request

from settings.llm_config import LLMConfigError, LLMConfigStore
from llm.provider_client import GeminiClient, LLMProviderError

llm_bp = Blueprint("llm_settings", __name__)


def get_llm_store():
    """Create the LLM configuration store."""
    return LLMConfigStore()


@llm_bp.get("/config")
def get_config():
    """Return all provider settings without exposing API keys."""
    try:
        return jsonify(get_llm_store().get_config())
    except LLMConfigError as exc:
        return jsonify({"error": str(exc)}), 500


@llm_bp.post("/providers/<provider_id>")
def save_provider(provider_id):
    """Save settings for one provider."""
    settings = request.get_json(silent=True)

    if not isinstance(settings, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    try:
        config = get_llm_store().save_provider(
            provider_id,
            settings,
        )
        return jsonify(config)
    except LLMConfigError as exc:
        return jsonify({"error": str(exc)}), 400


@llm_bp.post("/active")
def set_active_provider():
    """Set the active LLM provider."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    provider_id = data.get("provider_id")

    if not isinstance(provider_id, str) or not provider_id:
        return jsonify({"error": "A provider_id is required."}), 400

    try:
        config = get_llm_store().set_active_provider(provider_id)
        return jsonify(config)
    except LLMConfigError as exc:
        return jsonify({"error": str(exc)}), 400

@llm_bp.post("/test")
def test_provider():
    """Send a test prompt to the active LLM provider."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    prompt = data.get("prompt")

    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "A non-empty prompt is required."}), 400

    try:
        store = get_llm_store()
        config = store.get_config()

        if config.get("active_provider") != "google":
            return jsonify({
                "error": "Google Gemini is not the active provider."
            }), 400

        response = GeminiClient(config_store=store).generate(prompt)

        return jsonify({"response": response})

    except LLMProviderError as exc:
        return jsonify({"error": str(exc)}), 502
    except LLMConfigError as exc:
        return jsonify({"error": str(exc)}), 500