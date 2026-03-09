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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
