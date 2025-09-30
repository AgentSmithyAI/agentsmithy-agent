"""Configuration settings for AgentSmithy server."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow uppercase env vars like DEFAULT_MODEL to match lowercase fields
    )

    # OpenAI Configuration
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")

    # Server Configuration
    server_host: str = Field(default="localhost", description="Server host")
    server_port: int = Field(default=11434, description="Server port")

    # RAG Configuration
    chroma_persist_directory: str = Field(
        default="./chroma_db", description="Directory for ChromaDB persistence"
    )
    max_context_length: int = Field(
        default=10000, description="Maximum context length in characters"
    )
    max_open_files: int = Field(
        default=5, description="Maximum number of open files to include in context"
    )

    # Summarization threshold (single knob, tokens)
    summary_trigger_token_budget: int = Field(
        default=20000,
        description=(
            "Approximate total input tokens in dialog after which summarization should be applied"
        ),
        validation_alias="SUMMARY_TRIGGER_TOKEN_BUDGET",
    )

    # LLM Configuration
    default_model: str = Field(
        default="", description="Default LLM model", validation_alias="DEFAULT_MODEL"
    )
    default_temperature: float = Field(
        default=0.7,
        description="Default temperature for LLM",
        validation_alias="DEFAULT_TEMPERATURE",
    )
    # Reasoning controls (GPT-5)
    reasoning_effort: str | None = Field(
        default=None,
        description="Reasoning depth effort for GPT-5 (e.g., 'low', 'medium', 'high')",
        validation_alias="REASONING_EFFORT",
    )
    reasoning_verbosity: str | None = Field(
        default=None,
        description="Verbosity level for GPT-5 outputs (e.g., 'low', 'medium', 'high')",
        validation_alias="REASONING_VERBOSITY",
    )
    default_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Default embedding model",
        validation_alias="DEFAULT_EMBEDDING_MODEL",
    )
    max_tokens: int = Field(
        default=4000,
        description="Maximum tokens for LLM response",
        validation_alias="MAX_TOKENS",
    )
    streaming_enabled: bool = Field(
        default=True, description="Enable streaming responses"
    )

    # Web/HTTP Configuration
    web_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        description="Default User-Agent for outbound HTTP requests and headless browser contexts",
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    log_format: str = Field(default="pretty", description="Log format (pretty or json)")


# Global settings instance
settings = Settings()
