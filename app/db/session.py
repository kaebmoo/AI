from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings


def _create_engine(db_url: str):
    """Create SQLAlchemy engine with correct args for SQLite or PostgreSQL."""
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
    return create_engine(db_url, pool_pre_ping=True)


# ── App DB (users, sessions, chat_history) ────────────────────────
engine = _create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Config DB (schema_contexts, mappings, rules, hierarchy, etc.) ─
# If CONFIG_DB_URL is set, use separate DB; otherwise reuse app DB
# This keeps backward compatibility — existing deployments work without changes
if settings.CONFIG_DB_URL:
    config_engine = _create_engine(settings.CONFIG_DB_URL)
    ConfigSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=config_engine)
else:
    config_engine = engine
    ConfigSessionLocal = SessionLocal


# ── Business DB (revenue, expense, transfer_price — read-only views) ─
# Used by SchemaService for view inspection and MCP for query execution
import os
_bp = settings.BUSINESS_DB_PATH
if _bp:
    _business_url = _bp if _bp.startswith("sqlite") else f"sqlite:///{os.path.abspath(_bp)}"
    business_engine = _create_engine(_business_url)
else:
    business_engine = engine  # fallback: same as app DB


def get_db():
    """Dependency to get App DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_config_db():
    """Dependency to get Config DB session."""
    db = ConfigSessionLocal()
    try:
        yield db
    finally:
        db.close()
