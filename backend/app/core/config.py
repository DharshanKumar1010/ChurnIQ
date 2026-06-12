from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    APP_NAME: str = "ChurnIQ"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: PostgresDsn
    # Set True when connecting via Supabase pgBouncer (transaction mode,
    # port 6543). Disables SQLAlchemy's own pool so pgBouncer owns it.
    DB_USE_NULLPOOL: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30          # seconds before giving up on a connection
    DB_POOL_RECYCLE: int = 1800        # recycle connections after 30 min

    # ------------------------------------------------------------------
    # Security / JWT
    # ------------------------------------------------------------------
    SECRET_KEY: str                    # min 32-byte random string
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------
    # External APIs (Groq-compatible via OpenAI SDK)
    # ------------------------------------------------------------------
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    # Comma-separated extra origins injected at deploy time (e.g. Vercel domain).
    # Example: CORS_EXTRA_ORIGINS=https://churniq.vercel.app,https://churniq-git-main.vercel.app
    CORS_EXTRA_ORIGINS: str = ""

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        """Enforce a minimum key length to prevent weak secrets."""
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @model_validator(mode="after")
    def warn_debug_in_production(self) -> "Settings":
        """Prevent debug mode from leaking into production."""
        if self.ENVIRONMENT == "production" and self.DEBUG:
            raise ValueError("DEBUG must be False in production")
        if self.CORS_EXTRA_ORIGINS:
            extra = [o.strip() for o in self.CORS_EXTRA_ORIGINS.split(",") if o.strip()]
            self.ALLOWED_ORIGINS = list(set(self.ALLOWED_ORIGINS + extra))
        return self

    @property
    def async_database_url(self) -> str:
        """Return the DATABASE_URL with the asyncpg driver scheme."""
        url = str(self.DATABASE_URL)
        # Supabase / standard postgres → replace scheme for asyncpg
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (constructed once per process)."""
    return Settings()
