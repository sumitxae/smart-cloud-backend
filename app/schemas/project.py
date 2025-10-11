from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ProjectBase(BaseModel):
    name: str
    repo_url: str
    repo_full_name: str
    branch: str = "main"
    project_type: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    project_type: Optional[str] = None

class Project(ProjectBase):
    id: str
    user_id: str
    framework: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
