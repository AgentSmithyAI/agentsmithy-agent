"""Configuration settings for AgentSmithy server."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., description="OpenAI API key")
    
    # Server Configuration
    server_host: str = Field(default="localhost", description="Server host")
    server_port: int = Field(default=11434, description="Server port")
    
    # RAG Configuration
    chroma_persist_directory: str = Field(
        default="./chroma_db",
        description="Directory for ChromaDB persistence"
    )
    max_context_length: int = Field(
        default=10000,
        description="Maximum context length in characters"
    )
    max_open_files: int = Field(
        default=5,
        description="Maximum number of open files to include in context"
    )
    
    # LLM Configuration
    default_model: str = Field(
        default="gpt-4-turbo-preview",
        description="Default LLM model"
    )
    default_temperature: float = Field(
        default=0.7,
        description="Default temperature for LLM"
    )
    max_tokens: int = Field(
        default=4000,
        description="Maximum tokens for LLM response"
    )
    streaming_enabled: bool = Field(
        default=True,
        description="Enable streaming responses"
    )


# Global settings instance
settings = Settings() 