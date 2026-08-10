import os
from dotenv import load_dotenv
load_dotenv()

# Model registry: tag -> {model_id, provider, label}
MODEL_REGISTRY = {
    # ── DeepSeek ──────────────────────────────────
    "deepseek-v4-flash": {
        "model_id": "deepseek-v4-flash",
        "provider": "deepseek",
        "label": "DeepSeek V4 Flash"
    },
    "deepseek-v4-pro": {
        "model_id": "deepseek-v4-pro",
        "provider": "deepseek",
        "label": "DeepSeek V4 Pro"
    },

    # ── Google Gemini ─────────────────────────────
    "gemini-3.6-flash": {
        "model_id": "gemini-3.6-flash",
        "provider": "google",
        "label": "Gemini 3.6 Flash"
    },
    "gemini-3.5-flash": {
        "model_id": "gemini-3.5-flash",
        "provider": "google",
        "label": "Gemini 3.5 Flash"
    },
    "gemini-3.5-flash-lite": {
        "model_id": "gemini-3.5-flash-lite",
        "provider": "google",
        "label": "Gemini 3.5 Flash Lite"
    },
    "gemini-3.1-pro-preview": {
        "model_id": "gemini-3.1-pro-preview",
        "provider": "google",
        "label": "Gemini 3.1 Pro"
    },
    "gemini-3.1-flash-lite": {
        "model_id": "gemini-3.1-flash-lite",
        "provider": "google",
        "label": "Gemini 3.1 Flash Lite"
    },
    "gemini-3-flash-preview": {
        "model_id": "gemini-3-flash-preview",
        "provider": "google",
        "label": "Gemini 3 Flash (Preview)"
    },

    # ── Anthropic Claude ──────────────────────────
    "claude-sonnet-5": {
        "model_id": "claude-sonnet-5",
        "provider": "anthropic",
        "label": "Claude Sonnet 5"
    },
    "claude-opus-5": {
        "model_id": "claude-opus-5",
        "provider": "anthropic",
        "label": "Claude Opus 5"
    },
    "claude-opus-4-8": {
        "model_id": "claude-opus-4-8",
        "provider": "anthropic",
        "label": "Claude Opus 4.8"
    },
    "claude-opus-4-7": {
        "model_id": "claude-opus-4-7",
        "provider": "anthropic",
        "label": "Claude Opus 4.7"
    },
    "claude-opus-4-6": {
        "model_id": "claude-opus-4-6",
        "provider": "anthropic",
        "label": "Claude Opus 4.6"
    },
    "claude-sonnet-4-6": {
        "model_id": "claude-sonnet-4-6",
        "provider": "anthropic",
        "label": "Claude Sonnet 4.6"
    },
    "claude-haiku-4-5": {
        "model_id": "claude-haiku-4-5",
        "provider": "anthropic",
        "label": "Claude Haiku 4.5"
    },
    "claude-sonnet-4-5": {
        "model_id": "claude-sonnet-4-5",
        "provider": "anthropic",
        "label": "Claude Sonnet 4.5"
    },
    "claude-opus-4-5": {
        "model_id": "claude-opus-4-5",
        "provider": "anthropic",
        "label": "Claude Opus 4.5"
    },

    # ── OpenAI ────────────────────────────────────
    "gpt-5.6-sol": {
        "model_id": "gpt-5.6-sol",
        "provider": "openai",
        "label": "GPT-5.6 Sol"
    },
    "gpt-5.6-terra": {
        "model_id": "gpt-5.6-terra",
        "provider": "openai",
        "label": "GPT-5.6 Terra"
    },
    "gpt-5.6-luna": {
        "model_id": "gpt-5.6-luna",
        "provider": "openai",
        "label": "GPT-5.6 Luna"
    },
    "gpt-5.5": {
        "model_id": "gpt-5.5",
        "provider": "openai",
        "label": "GPT-5.5"
    },
    "gpt-5.4": {
        "model_id": "gpt-5.4",
        "provider": "openai",
        "label": "GPT-5.4"
    },
    "gpt-5.4-pro": {
        "model_id": "gpt-5.4-pro",
        "provider": "openai",
        "label": "GPT-5.4 Pro"
    },
    "gpt-5.4-mini": {
        "model_id": "gpt-5.4-mini",
        "provider": "openai",
        "label": "GPT-5.4 Mini"
    },
    "gpt-5.3-codex": {
        "model_id": "gpt-5.3-codex",
        "provider": "openai",
        "label": "GPT-5.3 Codex"
    },
}


def get_model_list():
    """Return all available models for the frontend dropdown."""
    return [
        {"tag": tag, "label": info["label"], "provider": info["provider"]}
        for tag, info in MODEL_REGISTRY.items()
    ]


async def get_models(api_key, model_tag="deepseek-v4-flash", temperature=0.5):
    info = MODEL_REGISTRY.get(model_tag)
    if not info:
        raise ValueError(f"Unknown model tag: {model_tag}")

    model_id = info["model_id"]
    provider = info["provider"]

    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        llm = ChatDeepSeek(
            model=model_id,
            temperature=temperature,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=api_key,
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    try:
        await llm.ainvoke([{"role": "user", "content": "Hello world"}])
        return llm
    except Exception as e:
        print(str(e))
        return None
