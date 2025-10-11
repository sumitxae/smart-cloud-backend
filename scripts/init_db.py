#!/usr/bin/env python3
"""Initialize database with tables"""

from app.database import engine, Base
from app.models import User, Project, Deployment, CloudAccount, Instance

def init_db():
    """Create all tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully!")

if __name__ == "__main__":
    init_db()
