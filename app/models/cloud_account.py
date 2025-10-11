from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base
import uuid

class CloudAccount(Base):
    __tablename__ = "cloud_accounts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # aws, gcp, azure
    
    # Encrypted credentials (should be encrypted in production!)
    credentials_encrypted = Column(Text, nullable=False)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    last_verified = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="cloud_accounts")
