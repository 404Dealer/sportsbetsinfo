"""Configuration management using Pydantic settings.

All configuration is loaded from environment variables with the
SPORTSBETS_ prefix. Supports .env files via python-dotenv.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration via environment variables.

    All settings use the SPORTSBETS_ prefix in environment variables.
    Example: SPORTSBETS_DB_PATH, SPORTSBETS_KALSHI_API_KEY, etc.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SPORTSBETS_",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    db_path: Path = Field(
        default=Path("data/sportsbets.db"),
        description="Path to SQLite database file",
    )

    # Kalshi API (https://kalshi.com/api) - RSA Key Authentication
    kalshi_api_key: str = Field(
        default="",
        description="Kalshi API key ID (from API keys page)",
    )
    kalshi_private_key_path: Path | None = Field(
        default=None,
        description="Path to Kalshi RSA private key file (.pem)",
    )
    kalshi_private_key_base64: str = Field(
        default="",
        description="Base64-encoded Kalshi RSA private key (alternative to file path for serverless)",
    )

    # The Odds API (https://the-odds-api.com)
    odds_api_key: str = Field(
        default="",
        description="The Odds API key",
    )

    # Versioning
    schema_version: str = Field(
        default="1.0.0",
        description="Current data schema version",
    )

    # Rate Limiting (requests per second)
    kalshi_rate_limit: int = Field(
        default=10,
        description="Kalshi API requests per second",
    )
    odds_api_rate_limit: int = Field(
        default=1,
        description="Odds API requests per second",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    @property
    def kalshi_configured(self) -> bool:
        """Check if Kalshi API is configured."""
        has_key_file = (
            self.kalshi_private_key_path
            and self.kalshi_private_key_path.exists()
        )
        has_key_base64 = bool(self.kalshi_private_key_base64)
        return bool(self.kalshi_api_key and (has_key_file or has_key_base64))

    @property
    def odds_api_configured(self) -> bool:
        """Check if The Odds API is configured."""
        return bool(self.odds_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses LRU cache to ensure settings are only loaded once.
    """
    return Settings()
