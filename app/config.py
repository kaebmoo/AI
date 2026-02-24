import secrets
from typing import List, Optional, Union, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, PostgresDsn, field_validator, validator

class Settings(BaseSettings):
    """
    Application Settings
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    PROJECT_NAME: str = "NT AI Assistant"
    API_V1_STR: str = "/api/v1"
    
    # Database
    # Support both SQLite and PostgreSQL
    # Example SQLite: sqlite:///./sql_app.db
    # Example Postgres: postgresql://user:pass@localhost:5432/db
    DATABASE_URL: str = "sqlite:///./nt_fi_report.sqlite"

    # Database Engine - explicit engine type for SQL syntax rules
    # Options: "sqlite", "postgresql", "mssql"
    # If not set, will be auto-detected from DATABASE_URL
    DB_ENGINE: Optional[str] = None
    
    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql",
            user=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_SERVER"),
            path=f"/{values.get('POSTGRES_DB') or ''}",
        )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    # Comma-separated list of allowed origins, e.g. "https://app.nt.th,https://admin.nt.th"
    # Use "*" only for local development (not recommended for production)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Security
    # REQUIRED: Set a strong random secret key in production via SECRET_KEY env variable
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = ""
    MAX_TOKENS: int = 1000
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_set(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "SECRET_KEY is not set. Generate one with: "
                "python -c \"import secrets; print(secrets.token_hex(32))\" "
                "and add it to your .env file."
            )
        if v == "YOUR_SECRET_KEY_HERE_CHANGE_IN_PROD":
            raise ValueError("SECRET_KEY must be changed from the placeholder value.")
        return v
    
    # AI Provider Settings
    AI_PROVIDER: str = "gemini" # claude, gemini, or matcha
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_AI_API_KEY: Optional[str] = None
    
    # Matcha AI (Internal Gateway)
    MATCHA_API_URL: Optional[str] = None
    MATCHA_AI_API_KEY: Optional[str] = None
    MATCHA_MODEL: str = "gpt-4o"
    # Set to False only for internal/self-signed cert environments (e.g. NT gateway dev)
    MATCHA_SSL_VERIFY: bool = True
    MATCHA_TIMEOUT: float = 60.0
    
    # Model Configuration
    GEMINI_MODEL: str = "gemini-2.0-flash-exp"
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # Claude Extended Thinking
    CLAUDE_EXTENDED_THINKING: bool = False
    CLAUDE_THINKING_BUDGET_TOKENS: int = 8000

    # Two-Pass SQL Generation
    TWO_PASS_ENABLED: bool = False

    # Value Lookup (keyword index search)
    VALUE_LOOKUP_ENABLED: bool = False

    # Vanna AI (RAG) Settings
    VANNA_CHROMA_PATH: str = "./chroma_db"
    VANNA_DISTANCE_THRESHOLD: float = 1.8

    METADATA_DB_PATH: Optional[str] = None # Defaults to DATABASE_URL path if None 

    
    # Allowed Domains
    # Comma-separated list of allowed email domains for OTP login
    # e.g. "nt.th,ntictsolution.com"
    # Leave empty to allow all domains (not recommended for production)
    ALLOWED_EMAIL_DOMAINS: List[str] = []
    
    # OTP Settings
    OTP_LENGTH: int = 6
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 3
    OTP_COOLDOWN_MINUTES: int = 1
    
    # Session Settings
    SESSION_EXPIRY_HOURS: int = 24
    SESSION_REFRESH_THRESHOLD_HOURS: int = 1
    
    # Email Settings
    EMAIL_HOST: str = "mock"
    EMAIL_PORT: int = 587
    EMAIL_USER: str = "user@example.com"
    EMAIL_PASSWORD: str = "password"
    EMAIL_FROM: str = "noreply@example.com"

    # Rate Limiting
    LOGIN_RATE_LIMIT: str = "5/minute"
    API_RATE_LIMIT: str = "60/minute"
    CHAT_RATE_LIMIT: str = "20/minute"

settings = Settings()
