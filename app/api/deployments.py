from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, AsyncIterator
import asyncio
import json
from datetime import datetime

from ..database import get_db
from ..models import User, Project, Deployment, DeploymentStatus
from ..schemas import (
    DeploymentCreate,
    DeploymentResponse
)
from .deps import get_current_user
from ..services.deployment_service import DeploymentService

router = APIRouter()

@router.post("/start", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def start_deployment(
    deployment_data: DeploymentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new deployment"""
    # Verify project exists and belongs to user
    project = db.query(Project).filter(
        Project.id == deployment_data.project_id,
        Project.user_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Create deployment record
    env_vars = {var.key: var.value for var in deployment_data.config.env_vars}
    
    deployment = Deployment(
        project_id=project.id,
        user_id=current_user.id,
        provider=deployment_data.config.provider,
        region=deployment_data.config.region,
        cpu=deployment_data.config.cpu,
        memory=deployment_data.config.memory,
        branch=deployment_data.branch,
        env_vars=env_vars,
        status=DeploymentStatus.PENDING,
        logs="[INFO] 🚀 Deployment initiated - preparing infrastructure...\n[INFO] Connecting to cloud provider...\n"
    )
    
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    
    # Start deployment in background
    deployment_service = DeploymentService(db)
    background_tasks.add_task(
        deployment_service.execute_deployment,
        deployment.id,
        project,
        current_user.access_token,
        deployment_data.branch
    )
    
    return deployment

@router.post("/{deployment_id}/retry", response_model=DeploymentResponse)
async def retry_deployment(
    deployment_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retry a failed deployment"""
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id,
        Deployment.user_id == current_user.id
    ).first()
    
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )
    
    if deployment.status not in [DeploymentStatus.FAILED, DeploymentStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only retry failed or cancelled deployments"
        )
    
    # Get the project
    project = db.query(Project).filter(Project.id == deployment.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Reset deployment status
    deployment.status = DeploymentStatus.PENDING
    deployment.logs = "[INFO] Deployment retry initiated...\n"
    deployment.error_message = None
    deployment.started_at = datetime.utcnow()
    deployment.completed_at = None
    db.commit()
    
    # Start redeployment in background (reuse existing infrastructure)
    deployment_service = DeploymentService(db)
    background_tasks.add_task(
        deployment_service.execute_redeployment,
        deployment.id,
        project,
        current_user.access_token,
        deployment  # Pass the deployment itself for reuse
    )
    
    return deployment

@router.post("/redeploy", response_model=DeploymentResponse)
async def redeploy_project(
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Redeploy a project on existing infrastructure"""
    project_id = request.get("project_id")
    deployment_id = request.get("deployment_id")
    
    if not project_id or not deployment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id and deployment_id are required"
        )
    
    # Get the project
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Get the existing deployment
    existing_deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id,
        Deployment.user_id == current_user.id
    ).first()
    
    if not existing_deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )
    
    # Create a new deployment with the same configuration
    new_deployment = Deployment(
        project_id=project.id,
        user_id=current_user.id,
        provider=existing_deployment.provider,
        region=existing_deployment.region,
        cpu=existing_deployment.cpu,
        memory=existing_deployment.memory,
        branch=existing_deployment.branch,
        env_vars=existing_deployment.env_vars,
        status=DeploymentStatus.PENDING,
        logs="[INFO] Redeployment initiated...\n",
        instance_id=existing_deployment.instance_id,  # Reuse existing instance
        public_ip=existing_deployment.public_ip  # Reuse existing IP
    )
    
    db.add(new_deployment)
    db.commit()
    db.refresh(new_deployment)
    
    # Start redeployment in background (reuse existing infrastructure)
    deployment_service = DeploymentService(db)
    background_tasks.add_task(
        deployment_service.execute_redeployment,
        new_deployment.id,
        project,
        current_user.access_token,
        existing_deployment  # Pass existing deployment for reuse
    )
    
    return new_deployment

@router.get("/{deployment_id}/status", response_model=DeploymentResponse)
async def get_deployment_status(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get deployment status with timeout protection"""
    from ..utils.db_utils import safe_db_query
    
    def _get_deployment():
        return db.query(Deployment).filter(
            Deployment.id == deployment_id,
            Deployment.user_id == current_user.id
        ).first()
    
    try:
        # Execute query with 5-second timeout
        deployment = await safe_db_query(db, _get_deployment, timeout_seconds=5)
        
        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found"
            )
        
        return deployment
        
    except Exception as e:
        if "timed out" in str(e):
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Status check timed out. Please try again."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving deployment status: {str(e)}"
        )

@router.get("/{deployment_id}/logs")
async def get_deployment_logs(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get deployment logs as JSON with timeout protection"""
    from ..utils.db_utils import safe_db_query
    
    def _get_deployment():
        return db.query(Deployment).filter(
            Deployment.id == deployment_id,
            Deployment.user_id == current_user.id
        ).first()
    
    try:
        # Execute query with 5-second timeout
        deployment = await safe_db_query(db, _get_deployment, timeout_seconds=5)
        
        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deployment not found"
            )
        
        return {
            "logs": deployment.logs or "",
            "status": deployment.status.value,
            "completed": deployment.status in [
                DeploymentStatus.SUCCESS,
                DeploymentStatus.FAILED,
                DeploymentStatus.CANCELLED
            ],
            "public_url": deployment.public_url
        }
        
    except Exception as e:
        if "timed out" in str(e):
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Logs retrieval timed out. Please try again."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving deployment logs: {str(e)}"
        )

@router.get("/{deployment_id}/logs/stream")
async def stream_deployment_logs(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stream deployment logs using Server-Sent Events with enhanced real-time support"""
    from ..utils.db_utils import safe_db_query
    
    # First, verify deployment exists with timeout
    def _get_initial_deployment():
        return db.query(Deployment).filter(
            Deployment.id == deployment_id,
            Deployment.user_id == current_user.id
        ).first()
    
    try:
        deployment = await safe_db_query(db, _get_initial_deployment, timeout_seconds=5)
    except Exception as e:
        if "timed out" in str(e):
            raise HTTPException(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                detail="Initial deployment check timed out"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking deployment: {str(e)}"
        )
    
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )
    
    async def event_generator() -> AsyncIterator[str]:
        last_buffer_position = 0
        sent_initial_logs = False
        deployment_service = None
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        try:
            # Create deployment service instance outside the loop
            from ..services.deployment_service import DeploymentService
            deployment_service = DeploymentService(db)
            
            while consecutive_errors < max_consecutive_errors:
                try:
                    # Create a fresh DB session for each iteration to avoid blocking
                    from ..database import SessionLocal
                    fresh_db = SessionLocal()
                    
                    try:
                        # Quick deployment refresh with timeout
                        def _refresh_deployment():
                            return fresh_db.query(Deployment).filter(
                                Deployment.id == deployment_id,
                                Deployment.user_id == current_user.id
                            ).first()
                        
                        # Use a very short timeout for refresh operations
                        current_deployment = await safe_db_query(
                            fresh_db, _refresh_deployment, timeout_seconds=3
                        )
                        
                        if not current_deployment:
                            # Deployment was deleted
                            break
                        
                        # Send initial logs if not sent yet
                        if not sent_initial_logs and current_deployment.logs:
                            initial_data = {
                                "logs": current_deployment.logs,
                                "status": current_deployment.status.value,
                                "type": "initial"
                            }
                            yield f"data: {json.dumps(initial_data)}\n\n"
                            sent_initial_logs = True
                        
                        # Get new logs from buffer (non-blocking)
                        try:
                            new_logs, current_position = deployment_service.get_new_logs(
                                deployment_id, last_buffer_position
                            )
                            
                            if new_logs:
                                data = {
                                    "logs": new_logs,
                                    "status": current_deployment.status.value,
                                    "type": "update"
                                }
                                yield f"data: {json.dumps(data)}\n\n"
                                last_buffer_position = current_position
                        except Exception:
                            # Buffer access failed, continue without it
                            pass
                        
                        # Send heartbeat to keep connection alive
                        if not new_logs:
                            heartbeat_data = {
                                "type": "heartbeat",
                                "status": current_deployment.status.value,
                                "timestamp": datetime.utcnow().isoformat()
                            }
                            yield f"data: {json.dumps(heartbeat_data)}\n\n"
                        
                        # If deployment is complete, send final status and close
                        if current_deployment.status in [
                            DeploymentStatus.SUCCESS,
                            DeploymentStatus.FAILED,
                            DeploymentStatus.CANCELLED
                        ]:
                            final_data = {
                                "logs": "",
                                "status": current_deployment.status.value,
                                "completed": True,
                                "public_url": current_deployment.public_url,
                                "type": "final"
                            }
                            yield f"data: {json.dumps(final_data)}\n\n"
                            break
                        
                        # Reset error counter on success
                        consecutive_errors = 0
                        
                    finally:
                        # Always close the fresh DB session
                        fresh_db.close()
                        
                except Exception as e:
                    consecutive_errors += 1
                    error_data = {
                        "type": "error",
                        "message": f"Streaming error (attempt {consecutive_errors}): {str(e)}",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    
                    if consecutive_errors >= max_consecutive_errors:
                        final_error_data = {
                            "type": "error",
                            "message": "Too many consecutive errors, stopping stream",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        yield f"data: {json.dumps(final_error_data)}\n\n"
                        break
                
                # Short polling interval
                await asyncio.sleep(0.5)
                
        except Exception as fatal_error:
            fatal_data = {
                "type": "fatal_error",
                "message": f"Fatal streaming error: {str(fatal_error)}",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(fatal_data)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@router.get("/", response_model=List[DeploymentResponse])
async def list_deployments(
    project_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List deployments for current user"""
    query = db.query(Deployment).filter(Deployment.user_id == current_user.id)
    
    if project_id:
        query = query.filter(Deployment.project_id == project_id)
    
    deployments = query.order_by(Deployment.created_at.desc()).all()
    return deployments

@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deployment(
    deployment_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete deployment and cleanup resources"""
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id,
        Deployment.user_id == current_user.id
    ).first()
    
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )
    
    # Cleanup cloud resources in background
    deployment_service = DeploymentService(db)
    background_tasks.add_task(
        deployment_service.cleanup_deployment,
        deployment.id
    )
    
    return None
