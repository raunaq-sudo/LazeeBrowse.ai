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
    "deepseek-v4": {
        "model_id": "deepseek-v4",
        "provider": "deepseek",
        "label": "DeepSeek V4"
    },
    "deepseek-r1": {
        "model_id": "deepseek-r1",
        "provider": "deepseek",
        "label": "DeepSeek R1"
    },
    "deepseek-chat": {
        "model_id": "deepseek-chat",
        "provider": "deepseek",
        "label": "DeepSeek Chat"
    },
    "deepseek-coder": {
        "model_id": "deepseek-coder",
        "provider": "deepseek",
        "label": "DeepSeek Coder"
    },

    # ── Google Gemini ─────────────────────────────
    "gemini-2.5-flash": {
        "model_id": "gemini-2.5-flash",
        "provider": "google",
        "label": "Gemini 2.5 Flash"
    },
    "gemini-2.5-pro": {
        "model_id": "gemini-2.5-pro",
        "provider": "google",
        "label": "Gemini 2.5 Pro"
    },
    "gemini-2.0-flash": {
        "model_id": "gemini-2.0-flash",
        "provider": "google",
        "label": "Gemini 2.0 Flash"
    },
    "gemini-2.0-flash-lite": {
        "model_id": "gemini-2.0-flash-lite",
        "provider": "google",
        "label": "Gemini 2.0 Flash Lite"
    },
    "gemini-1.5-pro": {
        "model_id": "gemini-1.5-pro",
        "provider": "google",
        "label": "Gemini 1.5 Pro"
    },
    "gemini-1.5-flash": {
        "model_id": "gemini-1.5-flash",
        "provider": "google",
        "label": "Gemini 1.5 Flash"
    },

    # ── Anthropic Claude ──────────────────────────
    "claude-sonnet-4-20250514": {
        "model_id": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "label": "Claude Sonnet 4"
    },
    "claude-opus-4-20250514": {
        "model_id": "claude-opus-4-20250514",
        "provider": "anthropic",
        "label": "Claude Opus 4"
    },
    "claude-3-5-sonnet-20241022": {
        "model_id": "claude-3-5-sonnet-20241022",
        "provider": "anthropic",
        "label": "Claude 3.5 Sonnet"
    },
    "claude-3-5-haiku-20241022": {
        "model_id": "claude-3-5-haiku-20241022",
        "provider": "anthropic",
        "label": "Claude 3.5 Haiku"
    },
    "claude-3-haiku-20240307": {
        "model_id": "claude-3-haiku-20240307",
        "provider": "anthropic",
        "label": "Claude 3 Haiku"
    },

    # ── OpenAI ────────────────────────────────────
    "gpt-4o": {
        "model_id": "gpt-4o",
        "provider": "openai",
        "label": "GPT-4o"
    },
    "gpt-4o-mini": {
        "model_id": "gpt-4o-mini",
        "provider": "openai",
        "label": "GPT-4o Mini"
    },
    "gpt-4-turbo": {
        "model_id": "gpt-4-turbo",
        "provider": "openai",
        "label": "GPT-4 Turbo"
    },
    "gpt-4": {
        "model_id": "gpt-4",
        "provider": "openai",
        "label": "GPT-4"
    },
    "gpt-3.5-turbo": {
        "model_id": "gpt-3.5-turbo",
        "provider": "openai",
        "label": "GPT-3.5 Turbo"
    },
    "o1": {
        "model_id": "o1",
        "provider": "openai",
        "label": "o1"
    },
    "o1-mini": {
        "model_id": "o1-mini",
        "provider": "openai",
        "label": "o1 Mini"
    },
    "o3": {
        "model_id": "o3",
        "provider": "openai",
        "label": "o3"
    },
    "o3-mini": {
        "model_id": "o3-mini",
        "provider": "openai",
        "label": "o3 Mini"
    },
    "o4-mini": {
        "model_id": "o4-mini",
        "provider": "openai",
        "label": "o4 Mini"
    },

    # ── OpenRouter (Free) ─────────────────────────
    "openrouter-free": {
        "model_id": "openrouter/free",
        "provider": "openrouter",
        "label": "OpenRouter Free (Auto)"
    },
    "nemotron-3-ultra-free": {
        "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "provider": "openrouter",
        "label": "Nemotron 3 Ultra (Free)"
    },
    "nemotron-3-nano-omni-free": {
        "model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "provider": "openrouter",
        "label": "Nemotron 3 Nano Omni (Free)"
    },
    "llama-3.3-70b-free": {
        "model_id": "meta-llama/llama-3.3-70b-instruct:free",
        "provider": "openrouter",
        "label": "Llama 3.3 70B (Free)"
    },
    "qwen-2.5-72b-free": {
        "model_id": "qwen/qwen-2.5-72b-instruct:free",
        "provider": "openrouter",
        "label": "Qwen 2.5 72B (Free)"
    },
    "deepseek-r1-free": {
        "model_id": "deepseek/deepseek-r1:free",
        "provider": "openrouter",
        "label": "DeepSeek R1 (Free)"
    },
    "phi-4-reasoning-free": {
        "model_id": "microsoft/phi-4-reasoning:free",
        "provider": "openrouter",
        "label": "Phi-4 Reasoning (Free)"
    },
    "gemma-3-27b-free": {
        "model_id": "google/gemma-3-27b-it:free",
        "provider": "openrouter",
        "label": "Gemma 3 27B (Free)"
    },

    # ── OpenRouter (Paid) ─────────────────────────
    "openrouter-auto": {
        "model_id": "openrouter/auto",
        "provider": "openrouter",
        "label": "OpenRouter Auto"
    },
    "claude-3.5-sonnet-or": {
        "model_id": "anthropic/claude-3.5-sonnet",
        "provider": "openrouter",
        "label": "Claude 3.5 Sonnet (OR)"
    },
    "gpt-4o-or": {
        "model_id": "openai/gpt-4o",
        "provider": "openrouter",
        "label": "GPT-4o (OR)"
    },
    "gemini-2.5-flash-or": {
        "model_id": "google/gemini-2.5-flash",
        "provider": "openrouter",
        "label": "Gemini 2.5 Flash (OR)"
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
    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    try:
        await llm.ainvoke([{"role": "user", "content": "Hello world"}])
        return llm
    except Exception as e:
        print(str(e))
        return None
