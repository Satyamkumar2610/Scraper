"""
config.py — Centralised application settings.

All values are loaded from environment variables (or .env file) via pydantic-settings.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration sourced from environment variables."""

    # ── API ──────────────────────────────────────────
    API_KEY: str = ""

    # ── PostgreSQL ───────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "agri_db"
    POSTGRES_USER: str = "agri_user"
    POSTGRES_PASSWORD: str = "agri_password"

    # ── Application ─────────────────────────────────
    LOG_LEVEL: str = "INFO"
    DEFAULT_PAGE_SIZE: int = 100

    # ── Data.gov.in specific ────────────────────────
    DATAGOVIN_BASE_URL: str = (
        "https://api.data.gov.in/resource/"
        "35be999b-0208-4354-b557-f6ca9a5355de"
    )
    DATAGOVIN_RESOURCE_ID: str = "35be999b-0208-4354-b557-f6ca9a5355de"

    # ── Directories ─────────────────────────────────
    RAW_DIR: str = "raw"
    EXPORT_DIR: str = "exports"
    LOG_DIR: str = "logs"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            f"?sslmode=require"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
