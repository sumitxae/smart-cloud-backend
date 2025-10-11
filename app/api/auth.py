from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt
import httpx

from ..database import get_db
from ..config import settings
from ..models import User
from ..schemas import User as UserSchema
from .deps import get_current_user
router = APIRouter()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

@router.get("/github/login")
async def github_login():
    """Redirect to GitHub OAuth"""
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
        f"&scope=repo,user"
    )
    return RedirectResponse(github_auth_url)

@router.get("/github/callback")
async def github_callback(code: str, db: Session = Depends(get_db)):
    """Handle GitHub OAuth callback"""
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
            }
        )
        
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get access token from GitHub"
            )
        
        token_data = token_response.json()
        github_access_token = token_data.get("access_token")
        
        if not github_access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token received from GitHub"
            )
        
        # Get user info from GitHub
        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {github_access_token}"}
        )
        
        if user_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from GitHub"
            )
        
        github_user = user_response.json()
        
        # Check if user exists
        user = db.query(User).filter(User.github_id == str(github_user["id"])).first()
        
        if not user:
            # Create new user
            user = User(
                github_id=str(github_user["id"]),
                username=github_user["login"],
                email=github_user.get("email"),
                avatar_url=github_user.get("avatar_url"),
                access_token=github_access_token
            )
            db.add(user)
        else:
            # Update existing user
            user.access_token = github_access_token
            user.username = github_user["login"]
            user.email = github_user.get("email")
            user.avatar_url = github_user.get("avatar_url")
            user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        # Create JWT token
        access_token = create_access_token(
            data={"sub": user.id},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        # Redirect to frontend with token
        frontend_url = f"{settings.FRONTEND_URL}/auth/callback?token={access_token}"
        return RedirectResponse(frontend_url)

@router.get("/me", response_model=UserSchema)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user info"""
    return current_user

@router.get("/github/repos")
async def get_github_repos(
    current_user: User = Depends(get_current_user)
):
    """Get user's GitHub repositories"""
    if not current_user.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub access token available"
        )
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {current_user.access_token}",
                "Accept": "application/vnd.github.v3+json"
            },
            params={
                "sort": "updated",
                "per_page": 100
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch repositories from GitHub"
            )
        
        repos = response.json()
        return repos

@router.get("/github/repos/{repo_name}/branches")
async def get_github_branches(
    repo_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get branches for a specific repository"""
    if not current_user.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub access token available"
        )
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/repos/{current_user.username}/{repo_name}/branches",
            headers={
                "Authorization": f"Bearer {current_user.access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch branches from GitHub"
            )
        
        branches = response.json()
        return branches