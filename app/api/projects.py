from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models import User, Project
from ..schemas import Project as ProjectSchema, ProjectCreate, ProjectUpdate
from .deps import get_current_user
from ..services.github_service import GitHubService

router = APIRouter()

@router.get("/", response_model=List[ProjectSchema])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all projects for current user"""
    projects = db.query(Project).filter(Project.user_id == current_user.id).all()
    return projects

@router.post("/", response_model=ProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new project"""
    # Verify user has access to repo
    github_service = GitHubService(current_user.access_token)
    
    try:
        repo_info = await github_service.get_repo_info(project_data.repo_full_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to access repository: {str(e)}"
        )
    
    # Check if project has required Docker files
    try:
        has_dockerfile = await github_service.check_file_exists(project_data.repo_full_name, "Dockerfile", project_data.branch)
        has_compose = await github_service.check_file_exists(project_data.repo_full_name, "docker-compose.yml", project_data.branch)
        
        if not has_dockerfile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project must have a Dockerfile in the root directory. Please add a Dockerfile to your project before deploying."
            )
            
        if not has_compose:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project must have a docker-compose.yml file in the root directory. Please add a docker-compose.yml file to your project before deploying."
            )
            
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to validate Docker files: {str(e)}"
        )
    
    # Detect framework if not provided
    framework = project_data.project_type
    if not framework:
        framework = await github_service.detect_framework(project_data.repo_full_name)
    
    project = Project(
        user_id=current_user.id,
        name=project_data.name,
        repo_url=project_data.repo_url,
        repo_full_name=project_data.repo_full_name,
        branch=project_data.branch,
        project_type=project_data.project_type,
        framework=framework
    )
    
    db.add(project)
    db.commit()
    db.refresh(project)
    
    return project

@router.get("/{project_id}", response_model=ProjectSchema)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific project"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project

@router.put("/{project_id}", response_model=ProjectSchema)
async def update_project(
    project_id: str,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a project"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    update_data = project_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    db.commit()
    db.refresh(project)
    
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a project"""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    db.delete(project)
    db.commit()
    
    return None