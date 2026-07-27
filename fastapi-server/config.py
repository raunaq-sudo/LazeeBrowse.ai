import os
from dotenv import load_dotenv
load_dotenv()

from langchain_deepseek import ChatDeepSeek

# Model registry: tag -> {model_id, provider, label}
MODEL_REGISTRY = {
    "deepseek-v4-flash": {
        "model_id": "deepseek-v4-flash",
        "provider": "deepseek",
        "label": "DeepSeek V4 Flash"
    },

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
    "openrouter-free": {
        "model_id": "openrouter/free",
        "provider": "openrouter",
        "label": "OpenRouter Free (Auto)"
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