"""
LFM2.5-VL Vision Tool — image understanding via LFM2.5-VL.

Uses LiquidAI/LFM2.5-VL-3B (MLX 8-bit, ~3.5 GB) to interpret images.
The tool can analyze a live browser screenshot, an attached image, or
a base64-encoded image passed directly.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from langchain.tools import tool


# ──────────────────────────────────────────────────────────────────────────────
# Model loading (lazy, cached)
# ──────────────────────────────────────────────────────────────────────────────

_model = None
_processor = None
_config = None


def _load_model():
    global _model, _processor, _config
    if _model is not None:
        return _model, _processor, _config

    try:
        from mlx_vlm import load as mlx_load
        from mlx_vlm.utils import load_config
    except ImportError:
        raise ImportError(
            "mlx_vlm is required for the LFM2.5-VL tool. "
            "Install it with: pip install mlx-vlm"
        )

    model_path = str(Path.home() / "Models" / "LFM2.5-VL-3B-MLX-8bit")
    if not Path(model_path).is_dir():
        raise FileNotFoundError(
            f"Model not found at {model_path}. "
            "Download it first: huggingface-cli download LiquidAI/LFM2.5-VL-3B-MLX-8bit"
        )

    _model, _processor = mlx_load(model_path)
    _config = load_config(model_path)
    return _model, _processor, _config


def _decode_image(source_b64: str):
    """Decode a base64 string into a PIL Image."""
    from PIL import Image
    img_bytes = base64.b64decode(source_b64)
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")


def _run_model(image, query: str) -> str:
    """Run LFM2.5-VL on a PIL Image with the given query."""
    model, processor, config = _load_model()

    try:
        from mlx_vlm import generate as mlx_generate
        from mlx_vlm.prompt_utils import apply_chat_template
    except ImportError:
        return "Error: mlx_vlm not installed."

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": query},
            ],
        }
    ]

    prompt = apply_chat_template(
        processor,
        config,
        messages,
        add_generation_prompt=True,
        num_images=1,
    )

    result = mlx_generate(
        model,
        processor,
        prompt=prompt,
        image=[image],
        temp=0.2,
        top_k=50,
        repetition_penalty=1.0,
        verbose=False,
    )
    return result.text.strip()


# ──────────────────────────────────────────────────────────────────────────────
# LangChain tool
# ──────────────────────────────────────────────────────────────────────────────


def build_uitars_tool(browser_command, log_chat, get_attached_images=None):
    """Return a LangChain tool for image understanding via LFM2.5-VL.

    Args:
        browser_command: async callable to send commands to the browser.
        log_chat: async callable to log messages.
        get_attached_images: optional callable returning a list of base64
            strings for images attached to the current session.
    """

    @tool
    async def uitars_describe(query: str, image_b64: str = "") -> str:
        """Analyze an image and answer a question about it using the LFM2.5-VL vision model.

        Provide a natural-language query describing what you want to know.
        Image source priority:
          1. If image_b64 is provided, that image is analyzed.
          2. If the user attached images to their message, the first
             attached image is analyzed.
          3. Otherwise, a live screenshot of the browser page is captured.

        Examples:
          - "What is this t-shirt design?" (with attached image)
          - "What elements are visible on this page?" (browser screenshot)
          - "Read all the text in this image"

        Returns the model's textual answer.
        """
        # ── 1. Load model ──────────────────────────────────────────
        try:
            _load_model()
        except (ImportError, FileNotFoundError) as e:
            return f"Error: {e}"

        # ── 2. Resolve image ──────────────────────────────────────
        source = "attached image" if (image_b64 or (get_attached_images and get_attached_images())) else "browser screenshot"
        await log_chat(f"[uitars] Query: {query} (source: {source})")
        try:
            if image_b64:
                image = _decode_image(image_b64)
            elif get_attached_images:
                attached = get_attached_images()
                if attached:
                    image = _decode_image(attached[0])
                else:
                    image = None
            else:
                image = None

            if image is None:
                ss_result = await browser_command("screenshot", {})
                if isinstance(ss_result, dict) and ss_result.get("error"):
                    return f"Screenshot failed: {ss_result['error']}"
                if not isinstance(ss_result, dict) or not ss_result.get("screenshot"):
                    return "Screenshot returned no image data."
                image = _decode_image(ss_result["screenshot"])
        except Exception as e:
            return f"Error decoding image: {e}"

        # ── 3. Run model ──────────────────────────────────────────
        try:
            answer = _run_model(image, query)
            await log_chat(f"[uitars] Result: {answer[:500]}")
            return answer
        except Exception as e:
            return f"Model inference failed: {e}"

    return uitars_describe
