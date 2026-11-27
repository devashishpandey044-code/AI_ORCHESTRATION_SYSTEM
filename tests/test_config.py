import pytest
from pydantic import ValidationError

from app.core.config import _DEV_DATABASE_URL, _DEV_SECRET, Settings, normalize_database_url

REAL_URL = "postgresql+psycopg://user:pw@db.example.com:5432/app?sslmode=require"
REAL_SECRET = "a-long-random-secret-for-tests-only-0123456789"


def make(**kw) -> Settings:
    base = {"env": "dev", "database_url": REAL_URL, "secret_key": REAL_SECRET}
    return Settings(_env_file=None, **(base | kw))


@pytest.mark.parametrize(
    "given,expected",
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h/d?sslmode=require", "postgresql+psycopg://u:p@h/d?sslmode=require"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("sqlite://", "sqlite://"),
    ],
)
def test_database_urls_are_made_to_use_the_psycopg_driver(given, expected):
    assert normalize_database_url(given) == expected


def test_settings_normalize_the_url_a_host_gives_us():
    settings = make(database_url="postgres://u:p@h/d?sslmode=require")
    assert settings.database_url == "postgresql+psycopg://u:p@h/d?sslmode=require"


def test_a_fully_configured_production_passes():
    make(env="prod").validate_for_runtime()


def test_production_refuses_the_development_secret():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        make(env="prod", secret_key=_DEV_SECRET).validate_for_runtime()


def test_production_refuses_the_development_database():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        make(env="prod", database_url=_DEV_DATABASE_URL).validate_for_runtime()


def test_production_with_the_real_model_needs_a_key():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        make(env="prod", llm_provider="anthropic").validate_for_runtime()
    make(env="prod", llm_provider="anthropic", anthropic_api_key="k").validate_for_runtime()


def test_development_is_not_strict():
    make(env="dev", secret_key=_DEV_SECRET, database_url=_DEV_DATABASE_URL).validate_for_runtime()


def test_max_users_defaults_to_no_limit_and_cannot_be_negative():
    assert make().max_users == 0
    assert make(max_users=50).max_users == 50
    with pytest.raises(ValidationError):
        make(max_users=-1)
