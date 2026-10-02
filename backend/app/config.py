"""Centralized config, loaded from environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Environment
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://quant:devpassword@localhost:5432/quantcopilot"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MIN: int = 60 * 24 * 7  # 7 days

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # LLM
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    # DeepSeek (OpenAI-compatible API) — primary LLM for research notes.
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_CACHE_TTL_HOURS: int = 24
    NEWS_CACHE_TTL_HOURS: int = 2  # news moves faster than research theses, so cache shorter

    # WxPusher (earnings pipeline WeChat notifications) — optional, unset = push disabled
    WXPUSHER_APP_TOKEN: str = ""
    WXPUSHER_UID: str = ""

    # Lark/Discord webhooks (backtest + paper-trade notifications) — optional, unset = push disabled
    LARK_WEBHOOK_URL: str = ""
    DISCORD_WEBHOOK_URL: str = ""


settings = Settings()
