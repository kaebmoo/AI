from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Check if SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    # SQLite
    engine = create_engine(
        settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True
    )
else:
    # PostgreSQL
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency to get DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
