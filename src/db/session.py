"""
Ten31 Thoughts - Database Session Management
Centralized engine and session factory. Engine is created once at import time.
"""

import os
from sqlalchemy.orm import Session, sessionmaker
from .models import get_engine, create_tables, Base

# Singleton engine — created once, reused everywhere
_db_path = os.getenv("DATABASE_URL", "sqlite:///data/ten31thoughts.db")
engine = get_engine(_db_path)

# Session factory bound to the singleton engine
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Initialize database tables. Call once at app startup."""
    create_tables(engine)


def get_db() -> Session:
    """
    FastAPI dependency that yields a database session.
    Usage: session: Session = Depends(get_db)
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
