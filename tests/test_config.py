import pytest
from pydantic import ValidationError
from app.config import Settings, get_settings


# Tests that default settings match specifications from the PRD
def test_default_settings():
    settings = Settings(_env_file=None)
    assert settings.GEMINI_MODEL == "gemini-2.5-flash"
    assert settings.MAX_EXTRACTION_RETRIES == 3
    assert settings.DATABASE_URL == "sqlite:///./clausely.db"
    assert settings.POLICY_MAX_LIABILITY_CAP_USD == 500000.0
    assert settings.POLICY_LIABILITY_ANNUAL_MULTIPLE == 2.0
    assert settings.POLICY_MIN_RENEWAL_NOTICE_DAYS == 30
    assert settings.POLICY_MIN_TERMINATION_NOTICE_DAYS == 30
    assert settings.POLICY_APPROVED_JURISDICTIONS == "US-DE,US-NY,US-CA,UK"
    assert settings.API_HOST == "0.0.0.0"
    assert settings.API_PORT == 8000


# Tests that environment variables properly override default values
def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")
    monkeypatch.setenv("MAX_EXTRACTION_RETRIES", "5")
    monkeypatch.setenv("POLICY_MAX_LIABILITY_CAP_USD", "750000.5")

    settings = Settings(_env_file=None)
    assert settings.GEMINI_MODEL == "gemini-1.5-pro"
    assert settings.MAX_EXTRACTION_RETRIES == 5
    assert settings.POLICY_MAX_LIABILITY_CAP_USD == 750000.5


# Tests parsing of comma-separated jurisdiction string with varying whitespace
def test_jurisdictions_parsing():
    settings = Settings(
        POLICY_APPROVED_JURISDICTIONS=" us-de , us-ny, uk , us-ca ",
        _env_file=None,
    )
    jurisdictions = settings.get_approved_jurisdictions()
    assert jurisdictions == ["US-DE", "US-NY", "UK", "US-CA"]


# Tests that non-numeric strings for integer fields raise a validation error
def test_invalid_type_raises_error(monkeypatch):
    monkeypatch.setenv("MAX_EXTRACTION_RETRIES", "not-a-number")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# Tests that get_settings caches the returned instance
def test_get_settings_caching():
    first_instance = get_settings()
    second_instance = get_settings()
    assert first_instance is second_instance
