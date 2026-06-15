"""Configuration for 小绪·自我观察日记."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    # Database: PostgreSQL (production) or SQLite (local dev)
    _raw_db_url = os.getenv("DATABASE_URL", "sqlite:///self_observation.db")
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False

    # DeepSeek (OpenAI-compatible)
    LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    KNOWLEDGE_BASE_MAX_CHARS = int(os.getenv("KB_MAX_CHARS", "1200"))

    @classmethod
    def llm_available(cls) -> bool:
        """Check if a valid-looking API key is configured."""
        key = cls.LLM_API_KEY
        return bool(key) and len(key) > 10 and not key.startswith("你的")
