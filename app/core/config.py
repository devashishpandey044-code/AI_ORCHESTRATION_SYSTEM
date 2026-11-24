from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Life Orchestrator"
    env: str = "dev"  # dev | test | prod
    database_url: str = "postgresql+psycopg://lifeos:lifeos@localhost:5432/lifeos"
    secret_key: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    log_level: str = "INFO"
    llm_provider: str = "fake"  # fake | anthropic
    llm_model: str = "claude-haiku-5-5"
    anthropic_api_key: str | None = None
    llm_timeout_seconds: float = 30.0

    def validate_for_runtime(self) -> None:
        if self.env == "prod" and self.secret_key == _DEV_SECRET:
            raise RuntimeError("SECRET_KEY must be set explicitly in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
