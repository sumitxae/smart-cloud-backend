from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json
from datetime import datetime

from ..database import get_db
from ..models import User, CloudAccount
from ..schemas import CloudCredentials, CloudProviderInfo, CostEstimate
from .deps import get_current_user
from ..services.cloud_pricing_service import CloudPricingService

router = APIRouter()

@router.get("/providers", response_model=List[CloudProviderInfo])
async def list_providers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available cloud providers and their configuration status"""
    providers_info = []
    
    # Check AWS
    aws_account = db.query(CloudAccount).filter(
        CloudAccount.user_id == current_user.id,
        CloudAccount.provider == "aws",
        CloudAccount.is_active == True
    ).first()
    
    providers_info.append({
        "provider": "aws",
        "is_configured": aws_account is not None,
        "regions": [
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "eu-west-1", "eu-central-1", "ap-southeast-1", "ap-northeast-1"
        ],
        "instance_types": {
            "t2.micro": "1 vCPU, 1GB RAM",
            "t2.small": "1 vCPU, 2GB RAM",
            "t2.medium": "2 vCPU, 4GB RAM"
        }
    })
    
    # Check GCP
    gcp_account = db.query(CloudAccount).filter(
        CloudAccount.user_id == current_user.id,
        CloudAccount.provider == "gcp",
        CloudAccount.is_active == True
    ).first()
    
    providers_info.append({
        "provider": "gcp",
        "is_configured": gcp_account is not None,
        "regions": [
            "us-east1", "us-west1", "us-central1",
            "europe-west1", "asia-southeast1", "asia-northeast1"
        ],
        "instance_types": {
            "e2-micro": "0.5 vCPU, 1GB RAM",
            "e2-small": "1 vCPU, 2GB RAM",
            "e2-medium": "2 vCPU, 4GB RAM"
        }
    })
    
    return providers_info

@router.post("/credentials", status_code=status.HTTP_201_CREATED)
async def save_credentials(
    credentials: CloudCredentials,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save cloud provider credentials"""
    # In production, encrypt credentials before storing!
    credentials_json = json.dumps(credentials.credentials)
    
    # Check if account exists
    account = db.query(CloudAccount).filter(
        CloudAccount.user_id == current_user.id,
        CloudAccount.provider == credentials.provider
    ).first()
    
    if account:
        account.credentials_encrypted = credentials_json
        account.updated_at = datetime.utcnow()
    else:
        account = CloudAccount(
            user_id=current_user.id,
            provider=credentials.provider,
            credentials_encrypted=credentials_json
        )
        db.add(account)
    
    db.commit()
    
    return {"message": f"{credentials.provider.upper()} credentials saved successfully"}

@router.get("/credentials/{provider}")
async def get_credentials(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get cloud provider credentials"""
    account = db.query(CloudAccount).filter(
        CloudAccount.user_id == current_user.id,
        CloudAccount.provider == provider,
        CloudAccount.is_active == True
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for {provider}"
        )
    
    credentials = json.loads(account.credentials_encrypted)
    return {"provider": provider, "credentials": credentials}

@router.delete("/credentials/{provider}")
async def delete_credentials(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete cloud provider credentials"""
    account = db.query(CloudAccount).filter(
        CloudAccount.user_id == current_user.id,
        CloudAccount.provider == provider
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for {provider}"
        )
    
    account.is_active = False
    db.commit()
    
    return {"message": f"{provider.upper()} credentials deleted successfully"}

@router.get("/providers/{provider}/regions")
async def get_provider_regions(
    provider: str,
    current_user: User = Depends(get_current_user)
):
    """Get available regions for a cloud provider"""
    pricing_service = CloudPricingService()
    
    if provider.lower() == "aws":
        regions = await pricing_service.get_aws_regions()
    elif provider.lower() == "gcp":
        regions = await pricing_service.get_gcp_regions()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported provider"
        )
    
    return {"regions": regions}

@router.get("/providers/{provider}/regions/{region}/instances")
async def get_provider_instances(
    provider: str,
    region: str,
    current_user: User = Depends(get_current_user)
):
    """Get available instance types for a cloud provider and region"""
    pricing_service = CloudPricingService()
    
    if provider.lower() == "aws":
        instances = await pricing_service.get_aws_instance_types(region)
    elif provider.lower() == "gcp":
        instances = await pricing_service.get_gcp_instance_types(region)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported provider"
        )
    
    return {"instances": instances}

@router.post("/estimate-cost", response_model=CostEstimate)
async def estimate_cost(
    request: dict,
    current_user: User = Depends(get_current_user)
):
    """Estimate deployment cost using dynamic pricing"""
    provider = request.get("provider")
    region = request.get("region")
    cpu = request.get("cpu")
    memory = request.get("memory")
    
    pricing_service = CloudPricingService()
    
    try:
        # Get dynamic pricing from cloud provider
        if provider.lower() == "aws":
            instances = await pricing_service.get_aws_instance_types(region)
        elif provider.lower() == "gcp":
            instances = await pricing_service.get_gcp_instance_types(region)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported provider"
            )
        
        # Find matching instance type
        hourly_cost = 0.01  # Default fallback
        for instance in instances:
            if instance["instance_type"] == cpu:
                hourly_cost = instance["hourly_price"]
                break
        
    except Exception as e:
        print(f"Error fetching dynamic pricing: {e}")
        # Fallback to static pricing
        cost_map = {
            "aws": {
                "t2.micro": 0.0052,
                "t2.small": 0.0104,
                "t2.medium": 0.0208,
            },
            "gcp": {
                "e2-micro": 0.0048,
                "e2-small": 0.0096,
                "e2-medium": 0.0192,
            }
        }
        hourly_cost = cost_map.get(provider, {}).get(cpu, 0.01)
    
    monthly_cost = hourly_cost * 24 * 30
    
    return {
        "provider": provider,
        "region": region,
        "cpu": cpu,
        "memory": memory,
        "estimated_hourly_cost": round(hourly_cost, 4),
        "estimated_monthly_cost": round(monthly_cost, 2)
    }
