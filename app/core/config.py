from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Similaris API"
    version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]
    database_url: str
    redis_url: str
    segment_max_words: int = Field(default=150, ge=1)
    lexical_cosine_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    lexical_jaccard_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    semantic_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reference_index_dir: str = "data/reference-index"
    reference_search_mode: Literal["semantic", "lexical"] = "semantic"
    reference_search_top_n: int = Field(default=5, ge=1)
    reference_search_semantic_threshold: float = Field(default=0.5, ge=-1.0, le=1.0)
    hybrid_tfidf_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    hybrid_jaccard_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    hybrid_lexical_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    hybrid_semantic_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    hybrid_classification_moderate_threshold: float = Field(
        default=0.4, ge=0.0, le=1.0
    )
    hybrid_classification_high_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0
    )
    hybrid_classification_very_high_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0
    )
    hybrid_suspicious_final_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0
    )
    hybrid_suspicious_semantic_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0
    )
    hybrid_suspicious_tfidf_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0
    )
    hybrid_suspicious_jaccard_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0
    )
    hybrid_top_n: int = Field(default=5, ge=1)
    upload_dir: str = "uploads"
    upload_max_file_size_mb: int = Field(default=20, ge=1)

    secret_key: str = Field(
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

settings = Settings()
