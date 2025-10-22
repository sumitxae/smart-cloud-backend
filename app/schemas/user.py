from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None

class UserCreate(UserBase):
    github_id: Optional[str] = None
    gitlab_id: Optional[str] = None
    github_access_token: Optional[str] = None
    gitlab_access_token: Optional[str] = None

class User(UserBase):
    id: str
    github_id: Optional[str] = None
    gitlab_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserInDB(User):
    github_access_token: Optional[str] = None
    gitlab_access_token: Optional[str] = None