# -*- coding: utf-8 -*-
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "argenprecios"

    # Concurrency
    max_concurrent_browsers: int = 2   # cuantos Chromium corren en paralelo (recurso pesado)
    max_concurrent_pages: int = 6      # paginas de categoria concurrentes en total (liviano)

    # Schedule
    schedule_hour_1: int = 6
    schedule_hour_2: int = 12

    # Retention
    ttl_days: int = 30

    # Retry
    retry_interval_minutes: int = 15
    max_retries: int = 3

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = ""  # si esta vacio, auth deshabilitada (util para desarrollo local)

    # Timezone
    tz: str = "America/Argentina/Buenos_Aires"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Allowlist (comma-separated Gmail addresses)
    allowed_emails: str = ""

    # Frontend base URL (used for OAuth redirect after login)
    frontend_url: str = "http://localhost:8000"

    # Cookie security (False for localhost, True for HTTPS prod)
    cookie_secure: bool = False

    @property
    def allowed_emails_set(self) -> set:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
