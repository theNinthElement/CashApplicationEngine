from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://cashapp:cashapp123@localhost:5432/cash_application"

    # Application
    app_name: str = "Cash Application Engine"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = True

    # Matching thresholds
    auto_match_threshold: float = 85.0
    manual_review_threshold: float = 60.0

    # Matching weights
    reference_match_weight: float = 40.0
    amount_match_weight: float = 35.0
    company_match_weight: float = 15.0
    date_match_weight: float = 10.0

    # Amount tolerance (percentage)
    amount_tolerance_percent: float = 0.01  # 1%

    # Journal entry defaults
    default_company_code: str = "1000"
    default_document_type: str = "SA"
    default_gl_account: str = "100000"
    default_currency: str = "EUR"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
