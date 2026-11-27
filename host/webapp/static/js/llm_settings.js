
(() => {
  const providerSelect = document.getElementById("llm-provider");
  const configContainer = document.getElementById("llm-provider-config");
  const fieldsContainer = document.getElementById("llm-provider-fields");
  const statusElement = document.getElementById("llm-connection-status");

  const testSection = document.getElementById("llm-test-section");
  const testPrompt = document.getElementById("llm-test-prompt");
  const testButton = document.getElementById("llm-test-button");
  const testResult = document.getElementById("llm-test-result");

  let testInProgress = false;

  if (!providerSelect || !configContainer || !fieldsContainer) {
    return;
  }

  const csrfToken = document.querySelector(
    'meta[name="csrf-token"]'
  )?.content || "";

  const providers = {
    openai: {
      name: "OpenAI",
      apiKeyRequired: true,
      fields: [
        { name: "api_key", label: "API Key", type: "password" },
        {
          name: "model",
          label: "Model",
          type: "select",
          options: [
            { value: "gpt-6.2-astra", label: "GPT-6.2 Astra" },
            { value: "gpt-6.2-sol", label: "GPT-6.2 Sol" },
            { value: "gpt-6.1-terra", label: "GPT-6.1 Terra" },
            { value: "gpt-6-luna", label: "GPT-6 Luna" },
            { value: "gpt-5.5", label: "GPT-5.5" }
          ]
        }
      ]
    },
    anthropic: {
      name: "Anthropic Claude",
      apiKeyRequired: true,
      fields: [
        { name: "api_key", label: "API Key", type: "password" },
        {
          name: "model",
          label: "Model",
          type: "select",
          options: [
            { value: "claude-opus-5-5", label: "Claude Opus 5.5" },
            { value: "claude-sonnet-5-5", label: "Claude Sonnet 5.5" },
            { value: "claude-haiku-5-5", label: "Claude Haiku 5.5" },
            { value: "claude-fable-5-2", label: "Claude Fable 5.2" }
          ]
        }
      ]
    },
    google: {
      name: "Google Gemini",
      apiKeyRequired: true,
      fields: [
        { name: "api_key", label: "API Key", type: "password" },
        {
          name: "model",
          label: "Model",
          type: "select",
          options: [
            { value: "gemini-3.8-flash", label: "Gemini 3.8 Flash (Recommended)" },
            { value: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash-Lite" },
            { value: "gemini-3.6-flash", label: "Gemini 3.6 Flash" },
            { value: "gemini-3.7-flash", label: "Gemini 3.7 Flash" }
          ]
        }
      ]
    },
    "self-hosted": {
      name: "Self-hosted / Custom API",
      apiKeyRequired: false,
      fields: [
        {
          name: "base_url",
          label: "API Endpoint",
          type: "url",
          placeholder: "http://localhost:11434/v1"
        },
        { name: "model", label: "Model", placeholder: "Model name or ID" },
        { name: "api_key", label: "API Key", type: "password" }
      ]
    }
  };

  let currentConfig = null;

  function setStatus(message, isError = false) {
    statusElement.textContent = message;
    statusElement.classList.toggle("error", isError);
  }

    function updateTestPanel() {
    const isGeminiActive =
      currentConfig?.active_provider === "google";

    testSection.hidden = !isGeminiActive;

    testButton.disabled =
      !isGeminiActive ||
      testInProgress ||
      !testPrompt.value.trim();
  }

  async function runGeminiTest() {
    const prompt = testPrompt.value.trim();

    if (!prompt || currentConfig?.active_provider !== "google") {
      return;
    }

    testInProgress = true;
    updateTestPanel();

    testResult.textContent = "Waiting for Gemini response...";
    setStatus("Sending test prompt to Google Gemini...");

    try {
      const result = await apiRequest("/settings/llm/test", {
        method: "POST",
        body: JSON.stringify({ prompt })
      });

      testResult.textContent = result.response;
      setStatus("Gemini test completed.");
    } catch (error) {
      testResult.textContent = `Error: ${error.message}`;
      setStatus(error.message, true);
    } finally {
      testInProgress = false;
      updateTestPanel();
    }
  }

  async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(options.method === "POST"
          ? {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrfToken
            }
          : {})
      }
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }

    return result;
  }

  function createField(field, savedValue = "") {
    const wrapper = document.createElement("div");
    wrapper.className = "llm-form-field";

    const label = document.createElement("label");
    label.textContent = field.label;
    label.htmlFor = `llm-${field.name}`;

    let input;

    if (field.type === "select") {
      input = document.createElement("select");

      field.options.forEach(option => {
        const element = document.createElement("option");
        element.value = option.value;
        element.textContent = option.label;
        input.appendChild(element);
      });
    } else {
      input = document.createElement("input");
      input.type = field.type || "text";
      input.placeholder = field.placeholder || "";
    }

    input.id = `llm-${field.name}`;
    input.name = field.name;
    input.value = savedValue || "";

    if (field.name === "model" || field.name === "base_url") {
      input.required = true;
    }

    if (field.name === "api_key") {
      input.autocomplete = "new-password";
    }

    wrapper.append(label, input);
    return wrapper;
  }

  function renderProvider(providerId) {
    updateTestPanel();
    fieldsContainer.replaceChildren();

    const provider = providers[providerId];
    configContainer.hidden = !provider;

    if (!provider) {
      return;
    }

    const saved = currentConfig?.providers?.[providerId] || {};

    const heading = document.createElement("h3");
    heading.textContent = provider.name;

    const form = document.createElement("form");
    form.id = "llm-provider-form";

    provider.fields.forEach(field => {
      const wrapper = createField(field, saved[field.name]);

      if (field.name === "api_key" && saved.api_key_configured) {
        const input = wrapper.querySelector("input");
        input.placeholder = "Stored API key – leave blank to keep it";
        input.required = false;
      } else if (field.name === "api_key" && provider.apiKeyRequired) {
        wrapper.querySelector("input").required = true;
      }

      form.appendChild(wrapper);
    });

    const actions = document.createElement("div");
    actions.className = "llm-actions";

    const saveButton = document.createElement("button");
    saveButton.type = "submit";
    saveButton.textContent = "Save Configuration";

    const activateButton = document.createElement("button");
    activateButton.type = "button";
    activateButton.textContent = "Set as Active Provider";
    activateButton.disabled = !saved.configured ||
      currentConfig?.active_provider === providerId;

    actions.append(saveButton, activateButton);
    form.appendChild(actions);

    const providerStatus = document.createElement("p");
    providerStatus.className = "muted";
    providerStatus.textContent = saved.configured
      ? currentConfig.active_provider === providerId
        ? "Currently active provider"
        : "Provider configured"
      : "Provider not configured";

    form.appendChild(providerStatus);
    fieldsContainer.append(heading, form);

    form.addEventListener("submit", async event => {
      event.preventDefault();

      const settings = {};
      new FormData(form).forEach((value, key) => {
        settings[key] = value;
      });

      saveButton.disabled = true;
      setStatus("Saving provider configuration...");

      try {
        currentConfig = await apiRequest(
          `/settings/llm/providers/${encodeURIComponent(providerId)}`,
          {
            method: "POST",
            body: JSON.stringify(settings)
          }
        );

        renderProvider(providerId);
        setStatus("Provider configuration saved.");
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        saveButton.disabled = false;
      }
    });

    activateButton.addEventListener("click", async () => {
      activateButton.disabled = true;
      setStatus("Activating provider...");

      try {
        currentConfig = await apiRequest("/settings/llm/active", {
          method: "POST",
          body: JSON.stringify({ provider_id: providerId })
        });

        renderProvider(providerId);
        setStatus(`${provider.name} is now active.`);
      } catch (error) {
        setStatus(error.message, true);
        activateButton.disabled = false;
      }
    });
  }

  testPrompt.addEventListener("input", updateTestPanel);
  testButton.addEventListener("click", runGeminiTest);

  async function loadConfig() {
    setStatus("Loading LLM configuration...");

    try {
      currentConfig = await apiRequest("/settings/llm/config");
      updateTestPanel();

      const activeProvider = currentConfig.active_provider;
      setStatus(
        activeProvider
          ? `Active provider: ${providers[activeProvider]?.name || activeProvider}`
          : "No active provider selected."
      );

      if (providerSelect.value) {
        renderProvider(providerSelect.value);
      }
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  providerSelect.addEventListener("change", () => {
    renderProvider(providerSelect.value);
  });

  loadConfig();
})();
