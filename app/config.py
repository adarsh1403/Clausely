from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM configuration
    GEMINI_API_KEY: str = "your-api-key"
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Extraction retry configuration
    MAX_EXTRACTION_RETRIES: int = 3

    # Database configuration
    DATABASE_URL: str = "sqlite:///./clausely.db"

    # Compliance policy thresholds
    POLICY_MAX_LIABILITY_CAP_USD: float = 500000.0
    POLICY_LIABILITY_ANNUAL_MULTIPLE: float = 2.0
    POLICY_MIN_RENEWAL_NOTICE_DAYS: int = 30
    POLICY_MIN_TERMINATION_NOTICE_DAYS: int = 30
    POLICY_APPROVED_JURISDICTIONS: str = "US-DE,US-NY,US-CA,UK"

    # Server configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Read values from .env file and ignore extra environment variables
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Returns approved jurisdictions as a clean list of uppercase strings
    def get_approved_jurisdictions(self) -> list[str]:
        # Split by comma and strip whitespace from each jurisdiction code
        items = [item.strip().upper() for item in self.POLICY_APPROVED_JURISDICTIONS.split(",")]
        return [item for item in items if item]


# Returns a cached instance of application settings
@lru_cache
def get_settings() -> Settings:
    return Settings()
