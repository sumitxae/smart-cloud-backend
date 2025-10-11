from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base
import uuid

class Instance(Base):
    __tablename__ = "instances"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deployment_id = Column(String, ForeignKey("deployments.id"), nullable=False)
    
    # Instance details
    instance_id = Column(String, nullable=False)  # Cloud provider instance ID
    instance_type = Column(String, nullable=False)  # t2.micro, e2-micro, etc.
    public_ip = Column(String, nullable=True)
    private_ip = Column(String, nullable=True)
    
    # Terraform state
    terraform_state = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    destroyed_at = Column(DateTime, nullable=True)
    
    # Relationships
    deployment = relationship("Deployment", back_populates="instance")
