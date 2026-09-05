import pytest

from database import LOCAL_DEVELOPMENT_DATABASE_URL, get_database_url


def test_database_url_uses_explicit_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/app")
    monkeypatch.setenv("APP_ENV", "production")

    assert get_database_url() == "postgresql+psycopg://user:pass@db:5432/app"


def test_sqlite_default_is_restricted_to_local_environments(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert get_database_url() == LOCAL_DEVELOPMENT_DATABASE_URL

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_database_url()
