
import boto3
from typing import Dict, List
from ...config import settings

class AWSProvider:
    def __init__(self):
        self.ec2_client = boto3.client(
            'ec2',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION
        )
    
    def list_regions(self) -> List[str]:
        """List available AWS regions"""
        response = self.ec2_client.describe_regions()
        return [region['RegionName'] for region in response['Regions']]
    
    def get_instance_types(self, region: str = None) -> Dict[str, str]:
        """Get available instance types"""
        return {
            "t2.micro": "1 vCPU, 1GB RAM - $0.0116/hour",
            "t2.small": "1 vCPU, 2GB RAM - $0.023/hour",
            "t2.medium": "2 vCPU, 4GB RAM - $0.0464/hour",
            "t3.micro": "2 vCPU, 1GB RAM - $0.0104/hour",
            "t3.small": "2 vCPU, 2GB RAM - $0.0208/hour",
            "t3.medium": "2 vCPU, 4GB RAM - $0.0416/hour",
        }
    
    def verify_credentials(self) -> bool:
        """Verify AWS credentials are valid"""
        try:
            self.ec2_client.describe_regions()
            return True
        except Exception:
            return False
    
    def get_instance_info(self, instance_id: str) -> Dict:
        """Get instance information"""
        response = self.ec2_client.describe_instances(
            InstanceIds=[instance_id]
        )
        
        if not response['Reservations']:
            return None
        
        instance = response['Reservations'][0]['Instances'][0]
        
        return {
            "instance_id": instance['InstanceId'],
            "state": instance['State']['Name'],
            "public_ip": instance.get('PublicIpAddress'),
            "private_ip": instance.get('PrivateIpAddress'),
            "instance_type": instance['InstanceType'],
            "launch_time": instance['LaunchTime'].isoformat()
        }
    
    def terminate_instance(self, instance_id: str):
        """Terminate an EC2 instance"""
        self.ec2_client.terminate_instances(InstanceIds=[instance_id])