from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None

class UserCreate(UserBase):
    github_id: str
    access_token: str

class User(UserBase):
    id: str
    github_id: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserInDB(User):
    access_token: str