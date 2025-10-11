import os
import json
import subprocess
from typing import Dict
from ..config import settings

class TerraformService:
    def __init__(self, provider: str, region: str):
        self.provider = provider
        self.region = region
        self.terraform_dir = os.path.join("terraform", provider)
        self.terraform_bin = settings.TERRAFORM_PATH
    
    async def provision(self, deployment_id: str, cpu: str, memory: str) -> Dict:
        """Provision infrastructure using Terraform"""
        workspace_dir = os.path.join(settings.WORKSPACE_DIR, f"tf_{deployment_id}")
        os.makedirs(workspace_dir, exist_ok=True)
        
        # Copy Terraform files
        self._copy_terraform_files(workspace_dir)
        
        # Initialize Terraform
        self._run_command(["init"], workspace_dir)
        
        # Apply with variables
        instance_type = self._get_instance_type(cpu, memory)
        
        vars = {
            "deployment_id": deployment_id,
            "region": self.region,
            "instance_type": instance_type
        }
        
        # Add provider-specific variables
        if self.provider == "gcp":
            vars["project_id"] = settings.GCP_PROJECT_ID
        
        var_args = []
        for key, value in vars.items():
            var_args.extend(["-var", f"{key}={value}"])
        
        # Apply
        self._run_command(["apply", "-auto-approve"] + var_args, workspace_dir)
        
        # Get outputs
        output = self._run_command(["output", "-json"], workspace_dir)
        outputs = json.loads(output)
        
        return {
            "instance_id": outputs["instance_id"]["value"],
            "instance_type": instance_type,
            "public_ip": outputs["public_ip"]["value"],
            "private_ip": outputs.get("private_ip", {}).get("value"),
            "terraform_state": self._get_state(workspace_dir)
        }
    
    async def destroy(self, deployment_id: str):
        """Destroy infrastructure"""
        workspace_dir = os.path.join(settings.WORKSPACE_DIR, f"tf_{deployment_id}")
        
        if os.path.exists(workspace_dir):
            self._run_command(["destroy", "-auto-approve"], workspace_dir)
    
    def _copy_terraform_files(self, dest_dir: str):
        """Copy Terraform configuration files"""
        import shutil
        src_dir = self.terraform_dir
        
        for file in os.listdir(src_dir):
            if file.endswith(".tf"):
                shutil.copy(os.path.join(src_dir, file), dest_dir)
    
    def _run_command(self, args: list, cwd: str) -> str:
        """Run Terraform command"""
        cmd = [self.terraform_bin] + args
        
        # Set up environment with cloud provider credentials
        env = os.environ.copy()
        
        if self.provider == "aws":
            env.update({
                'AWS_ACCESS_KEY_ID': settings.AWS_ACCESS_KEY_ID,
                'AWS_SECRET_ACCESS_KEY': settings.AWS_SECRET_ACCESS_KEY,
                'AWS_DEFAULT_REGION': settings.AWS_DEFAULT_REGION
            })
        elif self.provider == "gcp":
            # Use absolute path for GCP service account
            gcp_key_path = os.path.abspath(settings.GCP_SERVICE_ACCOUNT_PATH)
            env.update({
                'GOOGLE_APPLICATION_CREDENTIALS': gcp_key_path
            })
        
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,  # Don't raise exception, handle it manually
            env=env
        )
        
        if result.returncode != 0:
            error_msg = f"Terraform command failed with exit code {result.returncode}\n"
            error_msg += f"Command: {' '.join(cmd)}\n"
            error_msg += f"Working directory: {cwd}\n"
            error_msg += f"STDOUT: {result.stdout}\n"
            error_msg += f"STDERR: {result.stderr}\n"
            raise Exception(error_msg)
        
        return result.stdout
    
    def _get_instance_type(self, cpu: str, memory: str) -> str:
        """Map CPU/memory to instance type"""
        if self.provider == "aws":
            # If cpu is already an instance type (from dynamic API), use it directly
            if cpu.startswith("t") or cpu.startswith("m") or cpu.startswith("c"):
                return cpu
            # Legacy mapping for numeric values
            elif cpu == "0.5":
                return "t2.micro"
            elif cpu == "1":
                return "t2.small"
            elif cpu == "2":
                return "t2.medium"
        elif self.provider == "gcp":
            # If cpu is already an instance type (from dynamic API), use it directly
            if cpu.startswith("e2-") or cpu.startswith("n1-"):
                return cpu
            # Legacy mapping for numeric values
            elif cpu == "0.5":
                return "e2-micro"
            elif cpu == "1":
                return "e2-small"
            elif cpu == "2":
                return "e2-medium"
        
        return "t2.micro"  # Default
    
    def _get_state(self, workspace_dir: str) -> Dict:
        """Get Terraform state"""
        state_file = os.path.join(workspace_dir, "terraform.tfstate")
        
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)
        
        return {}
