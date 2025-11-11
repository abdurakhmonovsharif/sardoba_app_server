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

    OTP_STATIC_CODE: Optional[str] = Field(default="1234", env="OTP_STATIC_CODE")
    OTP_LENGTH: int = Field(default=6, ge=4, le=8)
    OTP_EXPIRATION_MINUTES: int = Field(default=5, ge=1)
    OTP_RATE_LIMIT_PER_HOUR: int = Field(default=5, ge=1)

    PASSWORD_HASHING_ROUNDS: int = Field(default=12, ge=4)

    LOG_LEVEL: str = Field(default="INFO")
    ENVIRONMENT: str = Field(default="development")

    CORS_ORIGINS: list[AnyHttpUrl] | list[str] = Field(default_factory=list)

    DEFAULT_ADMIN_NAME: str = Field(default="Sardoba Admin", env="DEFAULT_ADMIN_NAME")
    DEFAULT_ADMIN_PHONE: str = Field(default="+998931434413", env="DEFAULT_ADMIN_PHONE")
    DEFAULT_ADMIN_PASSWORD: str = Field(default="admin123", env="DEFAULT_ADMIN_PASSWORD")

    class Config:
        case_sensitive = True
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"

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


load_dotenv(ENV_FILE)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""

    return Settings()
