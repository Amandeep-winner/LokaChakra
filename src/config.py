from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SELF_USER_NAME: str = "SELF_USER"

    # Databases
    POSTGRES_USER: str = "lokachakra"
    POSTGRES_PASSWORD: str = "lokachakra_secure_pg"
    POSTGRES_DB: str = "lokachakra_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_URI: str = "postgresql+asyncpg://lokachakra:lokachakra_secure_pg@localhost:5432/lokachakra_db"
    POSTGRES_SYNC_URI: str = "postgresql://lokachakra:lokachakra_secure_pg@localhost:5432/lokachakra_db"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "lokachakra_secure_neo4j"

    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM & Transcription
    GROQ_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = "https://api.groq.com/openai/v1"

    # OSINT Web Recon
    SEARXNG_URL: str = "http://localhost:8080"
    TAVILY_API_KEY: Optional[str] = None

    # Telegram HITL Bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ALLOWED_USER_ID: Optional[int] = None


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
