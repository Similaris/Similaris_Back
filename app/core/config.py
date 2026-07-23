from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configurações da aplicação Similaris."""

    app_name: str = "Similaris API"
    version: str = "0.1.0"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    # Banco de dados (SQLite em dev; trocar por PostgreSQL via .env)
    database_url: str = "sqlite:///./similaris.db"

    # Autenticação JWT
    secret_key: str = "similaris-dev-secret-troque-em-producao"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    class Config:
        env_file = ".env"


settings = Settings()
