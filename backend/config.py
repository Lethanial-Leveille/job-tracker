from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./data/dev.db"
    anthropic_api_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Claude models — Sonnet for routine parsing, Opus for resume tailoring
    claude_default_model: str = "claude-sonnet-4-6"
    claude_tailoring_model: str = "claude-opus-4-7"


@lru_cache
def get_settings() -> Settings:
    return Settings()
