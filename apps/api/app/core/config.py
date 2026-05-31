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
    prompt_hash_secret: str = Field(default="change-me-prompt-hash-secret", alias="PROMPT_HASH_SECRET")
    prompt_hash_key_id: str = Field(default="dev-key-1", alias="PROMPT_HASH_KEY_ID")
    initial_admin_password: str = Field(default="Admin1234!ChangeMe", alias="PROMPTGUARD_INITIAL_ADMIN_PASSWORD")
    access_token_expires_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRES_MINUTES")
    refresh_token_expires_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRES_DAYS")
    refresh_token_idle_expires_days: int = Field(default=14, alias="REFRESH_TOKEN_IDLE_EXPIRES_DAYS")
    auth_rate_limit_requests: int = Field(default=10, alias="AUTH_RATE_LIMIT_REQUESTS")
    auth_rate_limit_window_seconds: int = Field(default=60, alias="AUTH_RATE_LIMIT_WINDOW_SECONDS")

    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("PROMPTGUARD_CORS_ORIGINS must not contain '*' when credentials are allowed")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
