import pytest

import config


def test_checkpoint_url_uses_postgres_database_url(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "CHECKPOINT_DATABASE_URL", None)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/app")

    assert config.get_checkpoint_database_url() == "postgresql://user:pass@db:5432/app"


def test_production_validation_requires_remote_rag_artifact(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "RAG_ARTIFACT_URI", None)
    monkeypatch.setattr(config, "RAG_ARTIFACT_VERSION", None)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/app")

    with pytest.raises(RuntimeError, match="RAG_ARTIFACT_URI"):
        config.validate_startup_configuration()
