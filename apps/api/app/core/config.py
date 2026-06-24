from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development", alias="PROMPTGUARD_ENV")
    api_public_url: str = Field(default="http://localhost:8000", alias="PROMPTGUARD_API_PUBLIC_URL")
    extension_api_url: str = Field(default="", alias="PROMPTGUARD_EXTENSION_API_URL")
    dashboard_public_url: str = Field(default="http://localhost:8000/dashboard/", alias="PROMPTGUARD_DASHBOARD_PUBLIC_URL")
    dashboard_static_dir: str = Field(default="/opt/promptguard/dashboard", alias="PROMPTGUARD_DASHBOARD_STATIC_DIR")
    cors_origins: str = Field(default="http://localhost:8000", alias="PROMPTGUARD_CORS_ORIGINS")
    cors_extension_origin_regex: str = Field(
        default=r"^chrome-extension://[a-p]{32}$",
        alias="PROMPTGUARD_CORS_EXTENSION_ORIGIN_REGEX",
    )

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
    classifier_runtime_enabled: bool = Field(default=False, alias="PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED")
    classifier_manifest_path: str = Field(default="", alias="PROMPTGUARD_CLASSIFIER_MANIFEST_PATH")
    ml_inference_queue_enabled: bool = Field(default=True, alias="PROMPTGUARD_ML_INFERENCE_QUEUE_ENABLED")
    ml_inference_queue_max_workers: int = Field(default=1, alias="PROMPTGUARD_ML_INFERENCE_QUEUE_MAX_WORKERS")
    ml_inference_queue_max_queue_size: int = Field(default=32, alias="PROMPTGUARD_ML_INFERENCE_QUEUE_MAX_QUEUE_SIZE")
    ml_inference_queue_timeout_ms: int = Field(default=3000, alias="PROMPTGUARD_ML_INFERENCE_QUEUE_TIMEOUT_MS")
    ml_inference_gpu_capacity_enabled: bool = Field(default=False, alias="PROMPTGUARD_ML_INFERENCE_GPU_CAPACITY_ENABLED")
    ml_inference_gpu_reserved_memory_mb: int = Field(default=1024, alias="PROMPTGUARD_ML_INFERENCE_GPU_RESERVED_MEMORY_MB")
    ml_inference_gpu_memory_per_worker_mb: int = Field(default=2048, alias="PROMPTGUARD_ML_INFERENCE_GPU_MEMORY_PER_WORKER_MB")
    verifier_runtime_enabled: bool = Field(default=False, alias="PROMPTGUARD_VERIFIER_RUNTIME_ENABLED")
    verifier_manifest_path: str = Field(default="", alias="PROMPTGUARD_VERIFIER_MANIFEST_PATH")
    torch_worker_payload_dir: str = Field(
        default="/tmp/promptguard-torch-payloads",
        alias="PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR",
    )
    torch_worker_python_path: str = Field(
        default="/opt/venvs/torch/bin/python",
        alias="PROMPTGUARD_TORCH_WORKER_PYTHON_PATH",
    )
    torch_worker_script_path: str = Field(
        default="/app/scripts/torch_context_worker.py",
        alias="PROMPTGUARD_TORCH_WORKER_SCRIPT_PATH",
    )
    paddle_worker_payload_dir: str = Field(
        default="/tmp/promptguard-paddle-payloads",
        alias="PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR",
    )
    paddle_worker_python_path: str = Field(
        default="/opt/venvs/paddle/bin/python",
        alias="PROMPTGUARD_PADDLE_WORKER_PYTHON_PATH",
    )
    paddle_worker_script_path: str = Field(
        default="/app/scripts/paddle_ocr_worker.py",
        alias="PROMPTGUARD_PADDLE_WORKER_SCRIPT_PATH",
    )
    worker_readiness_required: bool = Field(default=True, alias="PROMPTGUARD_WORKER_READINESS_REQUIRED")
    worker_readiness_timeout_ms: int = Field(default=15_000, alias="PROMPTGUARD_WORKER_READINESS_TIMEOUT_MS")
    temp_file_encryption_key: str = Field(default="", alias="PROMPTGUARD_TEMP_FILE_ENCRYPTION_KEY")
    temp_file_dir: str = Field(default=".promptguard-temp", alias="PROMPTGUARD_TEMP_FILE_DIR")
    temp_file_ttl_seconds: int = Field(default=900, gt=0, alias="PROMPTGUARD_TEMP_FILE_TTL_SECONDS")
    temp_file_max_bytes: int = Field(default=1_048_576, gt=0, alias="PROMPTGUARD_TEMP_FILE_MAX_BYTES")

    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("PROMPTGUARD_CORS_ORIGINS must not contain '*' when credentials are allowed")
        return origins

    def cors_extension_origin_regex_value(self) -> str | None:
        regex = self.cors_extension_origin_regex.strip()
        return regex or None

    def classifier_manifest_path_value(self) -> Path | None:
        path = self.classifier_manifest_path.strip()
        if not path:
            return None
        return Path(path)

    def verifier_manifest_path_value(self) -> Path | None:
        path = self.verifier_manifest_path.strip()
        if not path:
            return None
        return Path(path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
