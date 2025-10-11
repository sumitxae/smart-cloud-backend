from google.cloud import compute_v1
from google.oauth2 import service_account
from typing import Dict, List
from ...config import settings

class GCPProvider:
    def __init__(self):
        credentials = service_account.Credentials.from_service_account_file(
            settings.GCP_SERVICE_ACCOUNT_PATH
        )
        self.compute_client = compute_v1.InstancesClient(credentials=credentials)
        self.project_id = settings.GCP_PROJECT_ID
    
    def list_regions(self) -> List[str]:
        """List available GCP regions"""
        return [
            "us-central1", "us-east1", "us-west1", "us-west2",
            "europe-west1", "europe-west2", "asia-east1", "asia-southeast1"
        ]
    
    def get_machine_types(self, zone: str = None) -> Dict[str, str]:
        """Get available machine types"""
        return {
            "e2-micro": "0.5 vCPU, 1GB RAM - $0.0084/hour",
            "e2-small": "1 vCPU, 2GB RAM - $0.0168/hour",
            "e2-medium": "2 vCPU, 4GB RAM - $0.0336/hour",
            "n1-standard-1": "1 vCPU, 3.75GB RAM - $0.0475/hour",
            "n1-standard-2": "2 vCPU, 7.5GB RAM - $0.095/hour",
        }
    
    def verify_credentials(self) -> bool:
        """Verify GCP credentials are valid"""
        try:
            # Try to list instances to verify credentials
            request = compute_v1.AggregatedListInstancesRequest(
                project=self.project_id,
                max_results=1
            )
            self.compute_client.aggregated_list(request=request)
            return True
        except Exception:
            return False
    
    def get_instance_info(self, instance_name: str, zone: str) -> Dict:
        """Get instance information"""
        request = compute_v1.GetInstanceRequest(
            project=self.project_id,
            zone=zone,
            instance=instance_name
        )
        
        instance = self.compute_client.get(request=request)
        
        public_ip = None
        if instance.network_interfaces:
            access_configs = instance.network_interfaces[0].access_configs
            if access_configs:
                public_ip = access_configs[0].nat_i_p
        
        return {
            "instance_id": str(instance.id),
            "name": instance.name,
            "status": instance.status,
            "public_ip": public_ip,
            "machine_type": instance.machine_type.split('/')[-1],
            "creation_timestamp": instance.creation_timestamp
        }
    
    def delete_instance(self, instance_name: str, zone: str):
        """Delete a GCP instance"""
        request = compute_v1.DeleteInstanceRequest(
            project=self.project_id,
            zone=zone,
            instance=instance_name
        )
        self.compute_client.delete(request=request)