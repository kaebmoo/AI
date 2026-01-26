from typing import List, Optional, Union, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, PostgresDsn, validator

class Settings(BaseSettings):
    """
    Application Settings
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    PROJECT_NAME: str = "NT Revenue Assistant"
    API_V1_STR: str = "/api/v1"
    
    # Database
    # Support both SQLite and PostgreSQL
    # Example SQLite: sqlite:///./sql_app.db
    # Example Postgres: postgresql://user:pass@localhost:5432/db
    DATABASE_URL: str = "sqlite:///./nt_revenue.db"
    
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

    # Security
    SECRET_KEY: str = "YOUR_SECRET_KEY_HERE_CHANGE_IN_PROD"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    
    # Allowed Domains
    ALLOWED_EMAIL_DOMAINS: List[str] = ["nt.co.th", "ntplc.co.th"]
    
    # OTP Settings
    OTP_LENGTH: int = 6
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 3
    OTP_COOLDOWN_MINUTES: int = 1
    
    # Session Settings
    SESSION_EXPIRY_HOURS: int = 24
    SESSION_REFRESH_THRESHOLD_HOURS: int = 1
    
    # Email Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "your-email@gmail.com"
    SMTP_PASSWORD: str = "your-password"
    FROM_EMAIL: str = "noreply@nt.co.th"

    # Rate Limiting
    LOGIN_RATE_LIMIT: str = "5/minute"
    API_RATE_LIMIT: str = "60/minute"
    CHAT_RATE_LIMIT: str = "20/minute"

settings = Settings()
