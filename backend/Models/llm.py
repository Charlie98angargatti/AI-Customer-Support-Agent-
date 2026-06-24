"""
models/llm.py  (FIXED)
======================
Provides get_llm() — a LangChain-compatible LLM that LangGraph
can call .bind_tools() and .invoke() on.

YOUR SETUP: Qwen 2.5 1.5B Instruct via HuggingFace transformers
"""

import os
from dotenv import load_dotenv

load_dotenv()

_llm_instance = None


def get_llm(temperature: float = 0.0):
    """
    Returns a LangChain-compatible LLM instance (Ollama only).
    Singleton: loads once and reuses.
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    use_ollama = os.getenv("USE_OLLAMA", "true").lower() == "true"

    if not use_ollama:
        raise ValueError(
            "This setup is Ollama-only. Set USE_OLLAMA=true in .env"
        )

    _llm_instance = _load_ollama(temperature)
    return _llm_instance


def _load_ollama(temperature: float):
    """
    Connects to local Ollama server.
    Make sure: ollama serve is running
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        raise ImportError(
            "Missing dependency.\n"
            "Run: pip install langchain-ollama"
        )

    model_name = os.getenv("OLLAMA_MODEL", "mistral")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    print("===================================")
    print(f"🔗 Connecting to Ollama")
    print(f"🧠 Model: {model_name}")
    print(f"🌐 URL: {base_url}")
    print("===================================")

    return ChatOllama(
        model=model_name,
        base_url=base_url,
        temperature=temperature
    )


# Optional test run
if __name__ == "__main__":
    llm = get_llm()
    print("LLM loaded successfully!")

