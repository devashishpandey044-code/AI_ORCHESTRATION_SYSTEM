from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"
_DEV_DATABASE_URL = "postgresql+psycopg://lifeos:lifeos@localhost:5432/lifeos"


def normalize_database_url(url: str) -> str:
    """Hosting services hand out postgres:// or postgresql:// URLs. This app uses psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Life Orchestrator"
    env: str = "dev"  # dev | test | prod
    database_url: str = _DEV_DATABASE_URL
    secret_key: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    log_level: str = "INFO"
    llm_provider: str = "fake"  # fake | anthropic
    llm_model: str = "claude-haiku-5-5"
    anthropic_api_key: str | None = None
    llm_timeout_seconds: float = 30.0
    onboarding_daily_limit: int = 20
    crisis_region: str = "IN"  # IN | US | anything else
    roadblock_daily_limit: int = 20
    max_active_experiments: int = 3
    max_users: int = Field(default=0, ge=0)  # 0 means no limit on sign-ups

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    def validate_for_runtime(self) -> None:
        if self.env == "prod" and self.secret_key == _DEV_SECRET:
            raise RuntimeError("SECRET_KEY must be set explicitly in production")
        if self.env == "prod" and self.database_url == _DEV_DATABASE_URL:
            raise RuntimeError("DATABASE_URL must be set explicitly in production")
        if self.env == "prod" and self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY must be set when LLM_PROVIDER is anthropic")


@lru_cache
def get_settings() -> Settings:
    return Settings()
