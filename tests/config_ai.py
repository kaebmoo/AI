"""
NT Revenue Assistant - Configuration
=====================================
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class AIConfig:
    """AI Provider Configuration"""
    provider: str  # "claude" or "gemini"
    api_key: str
    model: Optional[str] = None
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass
class DatabaseConfig:
    """Database Configuration"""
    db_path: str = "revenue.db"
    metadata_db_path: Optional[str] = None


@dataclass
class AppConfig:
    """Application Configuration"""
    ai: AIConfig
    database: DatabaseConfig
    debug: bool = False
    language: str = "thai"


def get_config_from_env() -> AppConfig:
    """Load configuration from environment variables"""
    
    # Determine AI provider
    provider = os.getenv("AI_PROVIDER", "claude").lower()
    
    # Get API key based on provider
    if provider == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    elif provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY", "")
        model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    else:
        raise ValueError(f"Unknown AI_PROVIDER: {provider}")
    
    return AppConfig(
        ai=AIConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            max_tokens=int(os.getenv("AI_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.0"))
        ),
        database=DatabaseConfig(
            db_path=os.getenv("DATABASE_PATH", "revenue.db"),
            metadata_db_path=os.getenv("METADATA_DB_PATH")
        ),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        language=os.getenv("LANGUAGE", "thai")
    )


# Default configuration
default_config = AppConfig(
    ai=AIConfig(
        provider="claude",
        api_key="",
        model="claude-sonnet-4-20250514"
    ),
    database=DatabaseConfig(
        db_path="revenue.db"
    )
)
