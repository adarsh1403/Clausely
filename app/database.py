from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.config import get_settings

# Load configuration settings
settings = get_settings()

# Configure SQLite engine with multi-threading support for FastAPI
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

# Create session factory for database operations
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Initializes all database tables defined on Base metadata
def init_db(bind_engine=None) -> None:
    from app.models import Base
    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)


# Dependency generator yielding an active database session
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        # Guarantee session closure after request handling
        db.close()
