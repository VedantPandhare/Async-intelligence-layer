from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/standup_intel"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # Anthropic (LLM agents)
    anthropic_api_key: str = ""

    # HuggingFace (embeddings)
    hf_token: str = ""
    hf_embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768

    # GitHub
    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # Jira
    jira_client_id: str = ""
    jira_client_secret: str = ""

    # App
    secret_key: str = "dev-secret-key-change-in-production"
    encryption_key: str = ""
    jwt_secret: str = "dev-jwt-secret"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
