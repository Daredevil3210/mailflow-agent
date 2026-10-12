"""Create the DeepSeek model used by the learning notebooks and scripts."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_env(*, override: bool = True) -> bool:
    """Load this project's .env, independent of the working directory."""
    return load_dotenv(PROJECT_ROOT / ".env", override=override)


def create_chat_model(*, temperature: float = 0.0) -> ChatOpenAI:
    """Use DeepSeek's OpenAI-compatible API with thinking disabled.

    The course forces tool calls, which require non-thinking mode on DeepSeek.
    ChatOpenAI is the client library here; requests go to DeepSeek, not OpenAI.
    """
    load_project_env()
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key.startswith("your_"):
        raise ValueError(
            "Set DEEPSEEK_API_KEY in the project-root .env using a new private key."
        )
    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=temperature,
        extra_body={"thinking": {"type": "disabled"}},
        timeout=60,
        max_retries=1,
        max_tokens=4096,
        use_responses_api=False,
    )
