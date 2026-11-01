"""Check the local Ollama connection using the project's configured AI provider."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from aiwriter.ai_provider import ProviderError, generate_text
from aiwriter.config import load_settings

settings = load_settings(os.environ)
if not settings.ai_api_url or not settings.ai_model:
    raise SystemExit(
        "AI settings missing. Set AI_API_URL=http://127.0.0.1:11434/v1 "
        "and AI_MODEL=qwen3:1.7b in your local .env."
    )

print("AI endpoint:", settings.ai_api_url)
print("Model:", settings.ai_model)
print("Sending a short test prompt to the configured provider...")
try:
    result = generate_text(
        settings,
        "Write one short sentence introducing a helpful writing assistant.",
        "general",
        "english",
        "professional",
        "short",
    )
except ProviderError as exc:
    print("AI test failed:", exc.user_message)
    print("Check that Ollama is running and the model is installed: ollama list")
    raise SystemExit(1)

print("\nAI connection successful. Sample output:\n")
print(result[:1000])
