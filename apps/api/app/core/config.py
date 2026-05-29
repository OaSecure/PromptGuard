from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development", alias="PROMPTGUARD_ENV")
    api_public_url: str = Field(default="http://localhost:8000", alias="PROMPTGUARD_API_PUBLIC_URL")
    dashboard_public_url: str = Field(default="http://localhost:3000", alias="PROMPTGUARD_DASHBOARD_PUBLIC_URL")
    cors_origins: str = Field(default="http://localhost:3000", alias="PROMPTGUARD_CORS_ORIGINS")

    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")
    access_token_secret: str = Field(default="change-me-access-token-secret", alias="ACCESS_TOKEN_SECRET")
    refresh_token_secret: str = Field(default="change-me-refresh-token-secret", alias="REFRESH_TOKEN_SECRET")
    access_token_expires_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRES_MINUTES")
    refresh_token_expires_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRES_DAYS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
