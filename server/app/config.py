import os
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
_config: dict | None = None


def load_config(path: str | Path | None = None) -> dict:
    global _config
    p = Path(path) if path else _CONFIG_PATH
    with open(p) as f:
        _config = yaml.safe_load(f)
    return _config


def get_config() -> dict:
    if _config is None:
        return load_config()
    return _config


def get_llm_api_key() -> str:
    model: str = get_config()["llm"]["model"]
    if model.startswith("gemini/"):
        return os.environ.get("GEMINI_API_KEY", "")
    if model.startswith("openai/"):
        return os.environ.get("OPENAI_API_KEY", "")
    if model.startswith("openrouter/"):
        return os.environ.get("OPENROUTER_API_KEY", "")
    return os.environ.get("LLM_API_KEY", "")
