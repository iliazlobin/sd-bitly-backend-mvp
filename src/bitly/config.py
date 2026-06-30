from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://bitly:bitly@db:5432/bitly"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Rate limiting
    rate_limit_requests: int = 10
    rate_limit_window_s: int = 1

    # Server
    app_port: int = 8000
    app_host: str = "0.0.0.0"
