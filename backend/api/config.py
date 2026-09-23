from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ABR Intelligence Data API"
    app_version: str = "0.1.0"
    abr_api_key: str = ""
    abr_dashboard_read_key: str = ""
    abr_dashboard_password: str = ""
    abr_session_secret: str = ""


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
