from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aster_base_url: HttpUrl = Field(default="https://aster.gruposps.com.br/Login/abr")
    aster_login_email: str = ""
    aster_login_password: str = ""

    abr_ingest_url: str = ""
    abr_collector_key: str = ""
    abr_aster_fonte_id: str = ""
    abr_aster_entidade: str = "aster_relatorio"

    headless: bool = True
    browser_timeout_ms: int = 60_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
