from pydantic import BaseModel
from typing import Dict, List, Optional

class CloudCredentials(BaseModel):
    provider: str
    credentials: Dict[str, str]

class CloudProviderInfo(BaseModel):
    provider: str
    is_configured: bool
    regions: List[str]
    instance_types: Dict[str, str]

class CostEstimate(BaseModel):
    provider: str
    region: str
    cpu: str
    memory: str
    estimated_monthly_cost: float
    estimated_hourly_cost: float