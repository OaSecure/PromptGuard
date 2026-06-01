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
    dashboard_session_secret: str = Field(
        default="change-me-dashboard-session-secret",
        alias="DASHBOARD_SESSION_SECRET",
    )
    prompt_hash_secret: str = Field(default="change-me-prompt-hash-secret", alias="PROMPT_HASH_SECRET")
    prompt_hash_key_id: str = Field(default="dev-key-1", alias="PROMPT_HASH_KEY_ID")
    access_token_expires_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRES_MINUTES")
    refresh_token_expires_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRES_DAYS")
    dashboard_session_expires_hours: int = Field(default=12, alias="DASHBOARD_SESSION_EXPIRES_HOURS")
    dashboard_session_cookie_name: str = Field(
        default="promptguard_dashboard_session",
        alias="DASHBOARD_SESSION_COOKIE_NAME",
    )
    dashboard_csrf_cookie_name: str = Field(
        default="promptguard_dashboard_csrf",
        alias="DASHBOARD_CSRF_COOKIE_NAME",
    )
    dashboard_cookie_secure: bool = Field(default=False, alias="DASHBOARD_COOKIE_SECURE")
    dashboard_cookie_samesite: str = Field(default="lax", alias="DASHBOARD_COOKIE_SAMESITE")
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
