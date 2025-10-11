from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, List
from ..models.deployment import DeploymentStatus

class EnvVar(BaseModel):
    key: str
    value: str

class DeploymentConfig(BaseModel):
    provider: str = Field(..., description="Cloud provider: aws, gcp, or azure")
    region: str
    cpu: str
    memory: str
    env_vars: List[EnvVar] = []

class DeploymentCreate(BaseModel):
    project_id: str
    branch: str = "main"
    config: DeploymentConfig

class DeploymentUpdate(BaseModel):
    status: Optional[DeploymentStatus] = None
    logs: Optional[str] = None
    error_message: Optional[str] = None
    public_url: Optional[str] = None

class DeploymentResponse(BaseModel):
    id: str
    project_id: str
    provider: str
    region: str
    cpu: str
    memory: str
    status: DeploymentStatus
    public_url: Optional[str] = None
    public_ip: Optional[str] = None
    instance_id: Optional[str] = None
    deployment_time_seconds: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class DeploymentLogs(BaseModel):
    deployment_id: str
    logs: str
    status: DeploymentStatus
