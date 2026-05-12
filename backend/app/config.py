from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/standup_intel"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant — local dev uses host/port; Qdrant Cloud uses qdrant_url + qdrant_api_key
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_url: str = ""           # e.g. https://xxx.qdrant.io  (overrides host/port when set)
    qdrant_api_key: str = ""       # Qdrant Cloud API key

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
    slack_client_id: str = ""
    slack_client_secret: str = ""

    # Jira
    jira_client_id: str = ""
    jira_client_secret: str = ""

    # Email (SendGrid)
    sendgrid_api_key: str = ""
    email_from: str = "digest@standup.ai"

    # App
    secret_key: str = "dev-secret-key-change-in-production"
    encryption_key: str = ""
    jwt_secret: str = "dev-jwt-secret"
    environment: str = "development"
    event_retention_days: int = 90
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # URLs (used to build redirect links in OAuth and emails)
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # Analytics (PostHog — optional, gracefully skipped if unset)
    posthog_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
