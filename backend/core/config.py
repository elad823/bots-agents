from __future__ import annotations

import os
from pathlib import Path
from typing import List

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field

    class Settings(BaseSettings):
        gemini_api_key: str = Field(default="mock_dev_key", alias="GEMINI_API_KEY")
        gemini_model_default: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL_DEFAULT")
        environment: str = Field(default="development", alias="ENVIRONMENT")
        port: int = Field(default=8000, alias="PORT")
        database_path: str = Field(default="data/mas_database.db", alias="DATABASE_PATH")
        log_level: str = Field(default="INFO", alias="LOG_LEVEL")
        cors_origins: str = Field(default="http://localhost:8501,http://frontend:8501", alias="CORS_ORIGINS")
        max_rpm_limit: int = Field(default=14, alias="MAX_RPM_LIMIT")
        rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
        backend_api_url: str = Field(default="http://localhost:8000", alias="BACKEND_API_URL")

        @property
        def parsed_cors_origins(self) -> list[str]:
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"

except ImportError:
    class Settings:  # type: ignore
        """Fallback settings class when pydantic_settings is not installed."""
        def __init__(self) -> None:
            self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "mock_dev_key")
            self.gemini_model_default: str = os.getenv("GEMINI_MODEL_DEFAULT", "gemini-1.5-flash")
            self.environment: str = os.getenv("ENVIRONMENT", "development")
            self.port: int = int(os.getenv("PORT", "8000"))
            self.database_path: str = os.getenv("DATABASE_PATH", "data/mas_database.db")
            self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
            self.cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://frontend:8501")
            self.max_rpm_limit: int = int(os.getenv("MAX_RPM_LIMIT", "14"))
            self.rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
            self.backend_api_url: str = os.getenv("BACKEND_API_URL", "http://localhost:8000")

        @property
        def parsed_cors_origins(self) -> list[str]:
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Singleton instance
settings = Settings()
