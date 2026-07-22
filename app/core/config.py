from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações da aplicação Similaris."""

    app_name: str = "Similaris API"
    version: str = "0.1.0"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    class Config:
        env_file = ".env"


settings = Settings()
