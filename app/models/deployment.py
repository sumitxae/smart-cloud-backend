from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Integer, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base
import uuid
import enum

class DeploymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    CONFIGURING = "configuring"
    BUILDING = "building"
    DEPLOYING = "deploying"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Deployment(Base):
    __tablename__ = "deployments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Cloud configuration
    provider = Column(String, nullable=False)  # aws, gcp, azure
    region = Column(String, nullable=False)
    cpu = Column(String, nullable=False)
    memory = Column(String, nullable=False)
    branch = Column(String, nullable=False, default="main")
    
    # Deployment info
    status = Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING)
    instance_id = Column(String, nullable=True)
    public_url = Column(String, nullable=True)
    public_ip = Column(String, nullable=True)
    
    # Configuration
    env_vars = Column(JSON, default={})
    build_config = Column(JSON, default={})
    
    # Logs and metadata
    logs = Column(Text, default="")
    error_message = Column(Text, nullable=True)
    deployment_time_seconds = Column(Integer, nullable=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="deployments")
    instance = relationship("Instance", back_populates="deployment", uselist=False)
