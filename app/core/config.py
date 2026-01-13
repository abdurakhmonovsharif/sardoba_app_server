from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AnyHttpUrl, BaseSettings, Field, validator
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    PROJECT_NAME: str = "Sardoba Cashback App"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")

    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_REFRESH_SECRET_KEY: str = Field(..., env="JWT_REFRESH_SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=14, ge=1)

    OTP_STATIC_CODE: Optional[str] = Field(default=None, env="OTP_STATIC_CODE")
    OTP_LENGTH: int = Field(default=6, ge=4, le=8)
    OTP_EXPIRATION_MINUTES: int = Field(default=5, ge=1)
    OTP_RATE_LIMIT_PER_HOUR: int = Field(default=5, ge=1)
    RATE_LIMIT_BLOCK_MINUTES: int = Field(default=15, ge=1)
    LOGIN_RATE_LIMIT_PER_WINDOW: int = Field(default=5, ge=1)
    OTP_RATE_LIMIT_BYPASS_PHONES: list[str] = Field(
        default_factory=lambda: ["+998931434413"], env="OTP_RATE_LIMIT_BYPASS_PHONES"
    )
    OTP_BYPASS_VERIFY_PHONES: list[str] = Field(
        default_factory=lambda: ["+998931434413"], env="OTP_BYPASS_VERIFY_PHONES"
    )
    INTERNAL_DOCS_SECRET: Optional[str] = Field(default=None, env="INTERNAL_DOCS_SECRET")
    DEMO_PHONE: Optional[str] = Field(default="+998931434413", env="DEMO_PHONE")
    OTP_DEMO_CODE: str = Field(default="1111", env="OTP_DEMO_CODE")

    PASSWORD_HASHING_ROUNDS: int = Field(default=12, ge=4)

    LOG_LEVEL: str = Field(default="INFO")
    ENVIRONMENT: str = Field(default="development")
    LOG_FILE_PATH: str | None = Field(default="logs/app.log", env="LOG_FILE_PATH")
    SMS_DRY_RUN: bool = Field(default=False, env="SMS_DRY_RUN")

    IIKO_API_BASE_URL: str = Field(
        default="https://api-ru.iiko.services",
        env="IIKO_API_BASE_URL",
    )
    IIKO_API_LOGIN: str = Field(..., env="IIKO_API_LOGIN")
    IIKO_ORGANIZATION_ID: str = Field(..., env="IIKO_ORGANIZATION_ID")

    CORS_ORIGINS: list[AnyHttpUrl] | list[str] = Field(default_factory=list)

    DEFAULT_ADMIN_NAME: str = Field(default="Sardoba Admin", env="DEFAULT_ADMIN_NAME")
    DEFAULT_ADMIN_PHONE: str = Field(default="+998931434413", env="DEFAULT_ADMIN_PHONE")
    DEFAULT_ADMIN_PASSWORD: str = Field(default="admin123", env="DEFAULT_ADMIN_PASSWORD")

    PUBLIC_API_URL: str = Field(
        default="https://api.sardobacashback.uz",
        env="PUBLIC_API_URL",
    )

    ESKIZ_LOGIN: str = Field(..., env="ESKIZ_LOGIN")
    ESKIZ_PASSWORD: str = Field(..., env="ESKIZ_PASSWORD")
    ESKIZ_FROM_WHOM: str = Field(default="4546", env="ESKIZ_FROM_WHOM")
    ESKIZ_SMS_TEMPLATE: str = Field(
        default="Kod podtverjdeniya dlya vhoda v sistemu Restoran Sardoba - {code}. Pozhaluysta ne peredavayte drugim.",
        env="ESKIZ_SMS_TEMPLATE",
    )

    FCM_PROJECT_ID: str | None = Field(default=None, env="FCM_PROJECT_ID")
    FCM_SERVICE_ACCOUNT_FILE: str | None = Field(default=None, env="FCM_SERVICE_ACCOUNT_FILE")

    class Config:
        case_sensitive = True
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"

        @classmethod
        def parse_env_var(cls, field_name: str, raw_value: str):
            if field_name == "OTP_RATE_LIMIT_BYPASS_PHONES":
                # Let validator handle comma-separated strings instead of forcing JSON.
                return raw_value
            return super().parse_env_var(field_name, raw_value)

    @validator("CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            # Handle wildcard (allow all origins)
            v = v.strip().strip('"\'')  # Remove quotes if present
            if v == "*":
                return ["*"]
            # Otherwise split by comma
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @validator("OTP_RATE_LIMIT_BYPASS_PHONES", pre=True)
    def parse_rate_limit_bypass_phones(cls, v: str | list[str] | None) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            return [phone.strip() for phone in v.split(",") if phone.strip()]
        return v

    @validator("OTP_BYPASS_VERIFY_PHONES", pre=True)
    def parse_bypass_verify_phones(cls, v: str | list[str] | None) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            return [phone.strip() for phone in v.split(",") if phone.strip()]
        return v


load_dotenv(ENV_FILE)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""

    return Settings()
