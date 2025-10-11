import asyncio
import functools
from typing import Any, Callable, TypeVar
from sqlalchemy.orm import Session
from contextlib import contextmanager

T = TypeVar('T')

def with_db_timeout(timeout_seconds: int = 10):
    """Decorator to add timeout to database operations"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                # Run the function with timeout
                return await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, func, *args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise Exception(f"Database operation timed out after {timeout_seconds} seconds")
        return wrapper
    return decorator

@contextmanager
def db_session_with_timeout(db: Session, timeout_seconds: int = 30):
    """Context manager for database sessions with timeout"""
    try:
        # Set session timeout if supported
        if hasattr(db, 'execute'):
            try:
                # Try to set query timeout
                db.execute(f"SET statement_timeout = {timeout_seconds * 1000}")  # PostgreSQL
            except:
                pass  # Ignore if not PostgreSQL or not supported
        
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        try:
            db.close()
        except:
            pass

async def safe_db_query(db: Session, query_func: Callable, timeout_seconds: int = 10):
    """Execute database query with timeout and error handling"""
    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, query_func),
            timeout=timeout_seconds
        )
        return result
    except asyncio.TimeoutError:
        raise Exception(f"Database query timed out after {timeout_seconds} seconds")
    except Exception as e:
        raise Exception(f"Database query failed: {str(e)}")
