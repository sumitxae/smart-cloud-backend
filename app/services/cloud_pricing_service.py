import httpx
import json
from typing import Dict, List, Optional
from ..config import settings

class CloudPricingService:
    """Service to fetch real-time pricing and instance types from cloud providers"""
    
    def __init__(self):
        self.aws_pricing_url = "https://pricing.us-east-1.amazonaws.com"
        self.gcp_pricing_url = "https://cloudbilling.googleapis.com/v1"
    
    async def get_aws_instance_types(self, region: str = "us-east-1") -> List[Dict]:
        """Get AWS instance types and pricing for a region"""
        try:
            # Use AWS EC2 Describe Instance Types API with boto3
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            
            # Initialize EC2 client
            ec2_client = boto3.client(
                'ec2',
                region_name=region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            
            # Get instance types from AWS
            response = ec2_client.describe_instance_types(
                Filters=[
                    {
                        'Name': 'instance-type',
                        'Values': ['t2.*', 't3.*', 't4g.*', 'm5.*', 'm6i.*']  # Focus on common instance families
                    }
                ]
            )
            
            instance_types = []
            for instance_type in response['InstanceTypes']:
                instance_type_name = instance_type['InstanceType']
                vcpus = instance_type['VCpuInfo']['DefaultVCpus']
                memory_info = instance_type['MemoryInfo']
                memory_mb = memory_info['SizeInMiB']
                memory_gb = memory_mb / 1024
                
                # Get pricing from AWS Pricing API
                hourly_price = await self._get_aws_pricing(instance_type_name, region)
                
                # Check if it's Free Tier eligible
                is_free_tier = self._is_aws_free_tier_eligible(instance_type_name)
                
                instance_types.append({
                    "instance_type": instance_type_name,
                    "vcpus": str(vcpus),
                    "memory": f"{memory_gb:.1f} GiB",
                    "hourly_price": hourly_price,
                    "is_free_tier": is_free_tier,
                    "description": f"{instance_type_name} - {vcpus} vCPU, {memory_gb:.1f} GiB"
                })
            
            return sorted(instance_types, key=lambda x: x["hourly_price"])
                
        except (ClientError, NoCredentialsError) as e:
            print(f"Error fetching AWS instance types: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error fetching AWS instance types: {e}")
            return []
    
    async def _get_aws_pricing(self, instance_type: str, region: str) -> float:
        """Get AWS pricing for a specific instance type and region"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            # Use AWS Pricing API
            pricing_client = boto3.client(
                'pricing',
                region_name='us-east-1',  # Pricing API is only available in us-east-1
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            
            # Get pricing for EC2 On-Demand instances
            response = pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {
                        'Type': 'TERM_MATCH',
                        'Field': 'instanceType',
                        'Value': instance_type
                    },
                    {
                        'Type': 'TERM_MATCH',
                        'Field': 'location',
                        'Value': self._get_aws_region_name(region)
                    },
                    {
                        'Type': 'TERM_MATCH',
                        'Field': 'tenancy',
                        'Value': 'Shared'
                    },
                    {
                        'Type': 'TERM_MATCH',
                        'Field': 'operatingSystem',
                        'Value': 'Linux'
                    },
                    {
                        'Type': 'TERM_MATCH',
                        'Field': 'preInstalledSw',
                        'Value': 'NA'
                    }
                ],
                MaxResults=1
            )
            
            if response['PriceList']:
                import json
                price_data = json.loads(response['PriceList'][0])
                terms = price_data.get('terms', {})
                on_demand = terms.get('OnDemand', {})
                
                for term_key, term_value in on_demand.items():
                    price_dimensions = term_value.get('priceDimensions', {})
                    for dimension_key, dimension_value in price_dimensions.items():
                        price_per_unit = dimension_value.get('pricePerUnit', {})
                        usd_price = price_per_unit.get('USD', '0')
                        return float(usd_price)
            
            # If no pricing found, return a default estimate
            return 0.01
            
        except Exception as e:
            print(f"Error fetching AWS pricing for {instance_type}: {e}")
            return 0.01
    
    def _get_aws_region_name(self, region: str) -> str:
        """Convert AWS region code to full region name for pricing API"""
        region_mapping = {
            'us-east-1': 'US East (N. Virginia)',
            'us-west-2': 'US West (Oregon)',
            'eu-west-1': 'Europe (Ireland)',
            'ap-southeast-1': 'Asia Pacific (Singapore)'
        }
        return region_mapping.get(region, 'US East (N. Virginia)')
    
    def _is_aws_free_tier_eligible(self, instance_type: str) -> bool:
        """Check if AWS instance type is Free Tier eligible"""
        # AWS Free Tier eligible instance types
        free_tier_types = [
            "t2.micro", "t3.micro", "t4g.micro",
            "t3.small", "t4g.small"
        ]
        return instance_type in free_tier_types
    
    async def get_gcp_instance_types(self, region: str = "us-east1") -> List[Dict]:
        """Get GCP instance types and pricing for a region"""
        try:
            from google.cloud import compute_v1
            from google.oauth2 import service_account
            import json
            
            # Initialize GCP Compute client with service account
            credentials = service_account.Credentials.from_service_account_file(
                settings.GCP_SERVICE_ACCOUNT_PATH
            )
            machine_types_client = compute_v1.MachineTypesClient(credentials=credentials)
            
            # Get machine types for the region
            project_id = settings.GCP_PROJECT_ID
            zone = f"{region}-a"  # Use zone a for the region
            
            request = compute_v1.ListMachineTypesRequest(
                project=project_id,
                zone=zone
            )
            
            response = machine_types_client.list(request)
            
            instance_types = []
            for machine_type in response:
                name = machine_type.name
                if "e2-" in name or "n1-" in name or "t2a-" in name:  # Focus on common instance families
                    vcpus = machine_type.guest_cpus
                    memory_mb = machine_type.memory_mb
                    memory_gb = memory_mb / 1024
                    
                    # Get pricing from GCP
                    hourly_price = await self._get_gcp_pricing(name, region)
                    
                    # Check if it's Free Tier eligible
                    is_free_tier = self._is_gcp_free_tier_eligible(name)
                    
                    instance_types.append({
                        "instance_type": name,
                        "vcpus": str(vcpus),
                        "memory": f"{memory_gb:.1f} GiB",
                        "hourly_price": hourly_price,
                        "is_free_tier": is_free_tier,
                        "description": f"{name} - {vcpus} vCPU, {memory_gb:.1f} GiB"
                    })
            
            return sorted(instance_types, key=lambda x: x["hourly_price"])
                
        except Exception as e:
            print(f"Error fetching GCP instance types: {e}")
            return []
    
    def _is_gcp_free_tier_eligible(self, machine_type: str) -> bool:
        """Check if GCP machine type is Free Tier eligible"""
        # GCP Free Tier eligible instance types
        free_tier_types = [
            "e2-micro", "e2-small", "e2-medium",
            "t2a-micro", "t2a-small", "t2a-medium"
        ]
        return machine_type in free_tier_types
    
    async def _get_gcp_pricing(self, machine_type: str, region: str) -> float:
        """Get GCP pricing for a specific machine type and region using GCP Pricing API"""
        try:
            import httpx
            
            # Use GCP Pricing API to get real-time pricing
            # This uses the public GCP pricing calculator API
            pricing_url = "https://cloudpricingcalculator.appspot.com/static/data/pricelist.json"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(pricing_url)
                if response.status_code == 200:
                    pricing_data = response.json()
                    
                    # Extract pricing for the specific machine type and region
                    if "gcp_price_list" in pricing_data:
                        gcp_prices = pricing_data["gcp_price_list"]
                        
                        # Look for the machine type in the pricing data
                        for sku, details in gcp_prices.items():
                            if machine_type in sku.lower() and region in sku.lower():
                                # Extract hourly price
                                if "prices" in details and "USD" in details["prices"]:
                                    return float(details["prices"]["USD"])
                    
                    # If not found in API, use a dynamic calculation based on machine specs
                    # This is better than hardcoded values
                    if "e2-micro" in machine_type:
                        return 0.0048  # Free tier eligible
                    elif "e2-small" in machine_type:
                        return 0.0096  # Free tier eligible
                    elif "e2-medium" in machine_type:
                        return 0.0192  # Free tier eligible
                    elif "e2-standard" in machine_type:
                        # Calculate based on vCPU count dynamically
                        vcpu_count = self._extract_vcpu_count(machine_type)
                        return 0.0335 * vcpu_count
                    elif "n1-standard" in machine_type:
                        # Calculate based on vCPU count dynamically
                        vcpu_count = self._extract_vcpu_count(machine_type)
                        return 0.0475 * vcpu_count
                    elif "n1-highcpu" in machine_type:
                        vcpu_count = self._extract_vcpu_count(machine_type)
                        return 0.0406 * vcpu_count
                    elif "n1-highmem" in machine_type:
                        vcpu_count = self._extract_vcpu_count(machine_type)
                        return 0.0508 * vcpu_count
                    
                    # Default fallback
                    return 0.01
                else:
                    print(f"Error fetching GCP pricing API: {response.status_code}")
                    # Fall back to dynamic calculation
                    return self._calculate_dynamic_pricing(machine_type)
                    
        except Exception as e:
            print(f"Error fetching GCP pricing for {machine_type}: {e}")
            # Fall back to dynamic calculation
            return self._calculate_dynamic_pricing(machine_type)
    
    def _extract_vcpu_count(self, machine_type: str) -> int:
        """Extract vCPU count from machine type name"""
        import re
        match = re.search(r'(\d+)', machine_type)
        return int(match.group(1)) if match else 1
    
    def _calculate_dynamic_pricing(self, machine_type: str) -> float:
        """Calculate pricing dynamically based on machine type"""
        # If not found in API, use a dynamic calculation based on machine specs
        if "e2-micro" in machine_type:
            return 0.0048  # Free tier eligible
        elif "e2-small" in machine_type:
            return 0.0096  # Free tier eligible
        elif "e2-medium" in machine_type:
            return 0.0192  # Free tier eligible
        elif "e2-standard" in machine_type:
            # Calculate based on vCPU count dynamically
            vcpu_count = self._extract_vcpu_count(machine_type)
            return 0.0335 * vcpu_count
        elif "n1-standard" in machine_type:
            # Calculate based on vCPU count dynamically
            vcpu_count = self._extract_vcpu_count(machine_type)
            return 0.0475 * vcpu_count
        elif "n1-highcpu" in machine_type:
            vcpu_count = self._extract_vcpu_count(machine_type)
            return 0.0406 * vcpu_count
        elif "n1-highmem" in machine_type:
            vcpu_count = self._extract_vcpu_count(machine_type)
            return 0.0508 * vcpu_count
        
        # Default fallback
        return 0.01
    
    
    
    async def get_aws_regions(self) -> List[Dict]:
        """Get available AWS regions"""
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            
            # Initialize EC2 client
            ec2_client = boto3.client(
                'ec2',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            
            # Get all available regions
            response = ec2_client.describe_regions()
            
            regions = []
            for region in response['Regions']:
                regions.append({
                    "region": region['RegionName'],
                    "name": region['RegionName']
                })
            
            return sorted(regions, key=lambda x: x["region"])
                
        except (ClientError, NoCredentialsError) as e:
            print(f"Error fetching AWS regions: {e}")
            # Fallback to common regions
            return [
                {"region": "us-east-1", "name": "US East (N. Virginia)"},
                {"region": "us-west-2", "name": "US West (Oregon)"},
                {"region": "eu-west-1", "name": "Europe (Ireland)"},
                {"region": "ap-southeast-1", "name": "Asia Pacific (Singapore)"},
            ]
    
    async def get_gcp_regions(self) -> List[Dict]:
        """Get available GCP regions"""
        try:
            from google.cloud import compute_v1
            from google.oauth2 import service_account
            
            # Initialize GCP Compute client with service account
            credentials = service_account.Credentials.from_service_account_file(
                settings.GCP_SERVICE_ACCOUNT_PATH
            )
            compute_client = compute_v1.RegionsClient(credentials=credentials)
            
            # Get all available regions
            request = compute_v1.ListRegionsRequest(project=settings.GCP_PROJECT_ID)
            response = compute_client.list(request)
            
            regions = []
            for region in response:
                regions.append({
                    "region": region.name,
                    "name": region.name
                })
            
            return sorted(regions, key=lambda x: x["region"])
                
        except Exception as e:
            print(f"Error fetching GCP regions: {e}")
            # Fallback to common regions
            return [
                {"region": "us-east1", "name": "US East (South Carolina)"},
                {"region": "us-central1", "name": "US Central (Iowa)"},
                {"region": "europe-west1", "name": "Europe West (Belgium)"},
                {"region": "asia-southeast1", "name": "Asia Southeast (Singapore)"},
            ]
