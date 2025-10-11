from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings
import asyncio

# Configure engine with connection pooling and timeouts
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,           # Number of connections to maintain in pool
    max_overflow=20,        # Additional connections beyond pool_size
    pool_timeout=30,        # Timeout waiting for connection from pool
    pool_recycle=3600,      # Recycle connections after 1 hour
    pool_pre_ping=True,     # Validate connections before use
    connect_args={
        "connect_timeout": 10,  # Connection timeout
        "options": "-c statement_timeout=30000"  # 30 second query timeout
    } if "postgresql" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_with_timeout(timeout_seconds: int = 30):
    """Get database session with timeout"""
    async def _get_db():
        db = SessionLocal()
        try:
            # Set a timeout for the session
            future = asyncio.Future()
            
            def _run_with_db():
                try:
                    return db
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
                    raise
                finally:
                    if not future.done():
                        future.set_result(db)
            
            # Run with timeout
            try:
                yield await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, _run_with_db),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise Exception(f"Database operation timed out after {timeout_seconds} seconds")
        finally:
            db.close()
    
    return _get_db()