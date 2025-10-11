from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base
import uuid

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)
    repo_full_name = Column(String, nullable=False)  # e.g., "user/repo"
    branch = Column(String, default="main")
    project_type = Column(String, nullable=True)  # React, Python, etc.
    framework = Column(String, nullable=True)  # Detected framework
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    owner = relationship("User", back_populates="projects")
    deployments = relationship("Deployment", back_populates="project", cascade="all, delete-orphan")
