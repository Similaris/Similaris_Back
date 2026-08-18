from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration."""

    app_name: str = "Similaris API"
    version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]
    database_url: str = "sqlite:///./similaris.db"

    secret_key: str = Field(
        default="similaris-dev-secret-troque-em-producao",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "SECRET_KEY"),
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(
        default=480,
        validation_alias=AliasChoices(
            "JWT_ACCESS_TOKEN_EXPIRES_IN", "ACCESS_TOKEN_EXPIRE_MINUTES"
        ),
    )
    refresh_token_expire_minutes: int = Field(
        default=10080,
        validation_alias=AliasChoices("JWT_REFRESH_TOKEN_EXPIRES_IN"),
    )

    class Config:
        env_file = ".env"


settings = Settings()
