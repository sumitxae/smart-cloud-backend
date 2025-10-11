from datetime import datetime
from sqlalchemy.orm import Session
import asyncio
import threading
import socket
import subprocess

from ..models import Deployment, DeploymentStatus, Project, Instance
from ..config import settings
from .terraform_service import TerraformService
from .ansible_service import AnsibleService

class DeploymentService:
    def __init__(self, db: Session):
        self.db = db
        self.workspace_dir = settings.WORKSPACE_DIR
        self._log_buffers = {}  # Store log buffers for each deployment
        self._deployment_locks = {}  # Store locks for thread-safe logging
    
    def _get_deployment_lock(self, deployment_id: str):
        """Get or create a lock for a specific deployment"""
        if deployment_id not in self._deployment_locks:
            self._deployment_locks[deployment_id] = threading.Lock()
        return self._deployment_locks[deployment_id]
    
    def _log(self, deployment: Deployment, message: str, level: str = "INFO", flush_immediately: bool = False):
        """Add log message to deployment with real-time streaming support"""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}\n"
        
        with self._get_deployment_lock(deployment.id):
            # Add to database logs
            deployment.logs = (deployment.logs or "") + log_line
            
            # Buffer logs for streaming
            if deployment.id not in self._log_buffers:
                self._log_buffers[deployment.id] = []
            
            self._log_buffers[deployment.id].append(log_line)
            
            # Commit to database
            self.db.commit()
    
    def _log_verbose(self, deployment: Deployment, message: str, details: str = ""):
        """Add verbose log message with additional details"""
        if details:
            self._log(deployment, f"{message}\n{details}", level="DEBUG")
        else:
            self._log(deployment, message, level="DEBUG")
    
    def get_new_logs(self, deployment_id: str, last_position: int = 0) -> tuple[str, int]:
        """Get new logs since last position for streaming"""
        if deployment_id not in self._log_buffers:
            return "", 0
        
        with self._get_deployment_lock(deployment_id):
            buffer = self._log_buffers[deployment_id]
            new_logs = "".join(buffer[last_position:])
            return new_logs, len(buffer)
    
    def clear_log_buffer(self, deployment_id: str):
        """Clear log buffer for completed deployment"""
        if deployment_id in self._log_buffers:
            del self._log_buffers[deployment_id]
        if deployment_id in self._deployment_locks:
            del self._deployment_locks[deployment_id]
    
    async def _wait_for_ssh_ready(self, deployment: Deployment, host: str, port: int = 22, timeout: int = 300):
        """Wait for SSH to be ready on the instance"""
        self._log(deployment, f"Checking SSH connectivity to {host}:{port}")
        
        start_time = datetime.utcnow()
        attempt = 0
        
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            attempt += 1
            try:
                # Try to connect to SSH port
                self._log_verbose(deployment, f"Attempting SSH port check (attempt {attempt})")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    self._log(deployment, f"✓ SSH port {port} is open on {host}")
                    
                    # Additional check: try a simple SSH command with better error handling
                    try:
                        ssh_test_cmd = [
                            "ssh", 
                            "-i", "/tmp/deploy_key",
                            "-o", "StrictHostKeyChecking=no",
                            "-o", "UserKnownHostsFile=/dev/null",
                            "-o", "ConnectTimeout=10",
                            "-o", "BatchMode=yes",  # Prevents interactive prompts
                            f"ubuntu@{host}",
                            "echo 'SSH ready'"
                        ]
                        
                        self._log_verbose(deployment, f"Testing SSH authentication to {host}")
                        result = subprocess.run(
                            ssh_test_cmd,
                            capture_output=True,
                            text=True,
                            timeout=15
                        )
                        
                        if result.returncode == 0:
                            self._log(deployment, f"✓ SSH authentication successful to {host}")
                            return
                        else:
                            self._log_verbose(deployment, f"SSH auth test failed (attempt {attempt}): {result.stderr}")
                            
                    except subprocess.TimeoutExpired:
                        self._log_verbose(deployment, f"SSH test timed out (attempt {attempt})")
                    except FileNotFoundError:
                        # SSH command not found, skip the auth test but continue
                        self._log_verbose(deployment, "SSH command not found, skipping auth test")
                        self._log(deployment, "✓ SSH port is open, proceeding without auth test")
                        return
                    except Exception as e:
                        self._log_verbose(deployment, f"SSH test error (attempt {attempt}): {e}")
                        
                else:
                    self._log_verbose(deployment, f"SSH port not ready, connection failed with code {result} (attempt {attempt})")
                    
            except Exception as e:
                self._log_verbose(deployment, f"Connection check error (attempt {attempt}): {e}")
            
            # Wait before next attempt - shorter intervals initially
            if attempt <= 3:
                wait_time = 5  # First few attempts wait 5 seconds
            else:
                wait_time = min(10 + (attempt * 2), 30)  # Progressive backoff, max 30 seconds
                
            self._log_verbose(deployment, f"Waiting {wait_time} seconds before next attempt...")
            await asyncio.sleep(wait_time)
        
        # If we get here, SSH never became ready
        raise Exception(f"SSH connection to {host} not ready after {timeout} seconds. Instance may not be fully booted or SSH key may be incorrect.")
    
    def _update_status(self, deployment: Deployment, status: DeploymentStatus):
        """Update deployment status"""
        deployment.status = status
        deployment.updated_at = datetime.utcnow()
        self.db.commit()
        self._log(deployment, f"Status updated to: {status.value}", level="INFO")
    
    async def execute_deployment(
        self,
        deployment_id: str,
        project: Project,
        github_token: str,
        branch: str
    ):
        """Execute full deployment pipeline with enhanced logging"""
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        
        if not deployment:
            return
        
        start_time = datetime.utcnow()
        
        try:
            self._log(deployment, "🚀 Starting deployment pipeline", level="INFO")
            self._log_verbose(deployment, "Deployment details:", 
                            f"Project: {project.name}\nBranch: {branch}\nProvider: {deployment.provider}\nRegion: {deployment.region}")
            
            # 1. Provision infrastructure with Terraform
            self._log(deployment, f"🏗️ Provisioning {deployment.provider.upper()} infrastructure...")
            self._update_status(deployment, DeploymentStatus.PROVISIONING)
            
            terraform_service = TerraformService(deployment.provider, deployment.region)
            
            instance_info = await terraform_service.provision(
                deployment_id=deployment.id,
                cpu=deployment.cpu,
                memory=deployment.memory
            )
            
            # Save instance info
            instance = Instance(
                deployment_id=deployment.id,
                instance_id=instance_info["instance_id"],
                instance_type=instance_info["instance_type"],
                public_ip=instance_info["public_ip"],
                private_ip=instance_info.get("private_ip"),
                terraform_state=instance_info.get("terraform_state")
            )
            self.db.add(instance)
            
            deployment.instance_id = instance_info["instance_id"]
            deployment.public_ip = instance_info["public_ip"]
            self.db.commit()
            
            self._log(deployment, f"✓ Infrastructure provisioned: {instance_info['instance_id']}")
            self._log(deployment, f"   Public IP: {instance_info['public_ip']}")
            self._log_verbose(deployment, "Instance details:", 
                            f"Instance Type: {instance_info['instance_type']}\nPrivate IP: {instance_info.get('private_ip', 'N/A')}")
            
            # Wait for instance to be ready for SSH connections
            self._log(deployment, "⏳ Waiting for instance to be ready...")
            await self._wait_for_ssh_ready(deployment, instance_info["public_ip"])
            
            # 2. Configure instance with Ansible
            self._log(deployment, "⚙️ Configuring instance...")
            self._update_status(deployment, DeploymentStatus.CONFIGURING)
            
            ansible_service = AnsibleService()
            
            # Pass callback for real-time logging
            await ansible_service.configure_instance(
                host=instance_info["public_ip"],
                repo_url=f"https://github.com/{project.repo_full_name}.git",
                branch=branch,
                env_vars=deployment.env_vars,
                framework=project.framework,
                project_dir=None,
                log_callback=lambda msg: self._log_verbose(deployment, msg)
            )
            
            self._log(deployment, "✓ Instance configured successfully")
            
            # 3. Build application
            self._log(deployment, "🔨 Building application...")
            self._update_status(deployment, DeploymentStatus.BUILDING)
            
            await ansible_service.build_application(
                host=instance_info["public_ip"],
                framework=project.framework,
                project_dir=None,
                log_callback=lambda msg: self._log_verbose(deployment, msg)
            )
            
            self._log(deployment, "✓ Application built successfully")
            
            # 4. Deploy application
            self._log(deployment, "🚀 Deploying application...")
            self._update_status(deployment, DeploymentStatus.DEPLOYING)
            
            app_url = await ansible_service.deploy_application(
                host=instance_info["public_ip"],
                framework=project.framework,
                project_dir=None,
                log_callback=lambda msg: self._log_verbose(deployment, msg)
            )
            
            deployment.public_url = app_url or f"http://{instance_info['public_ip']}"
            self.db.commit()
            
            self._log(deployment, f"✓ Application deployed: {deployment.public_url}")
            
            # 5. Complete deployment
            end_time = datetime.utcnow()
            deployment_time = (end_time - start_time).total_seconds()
            
            deployment.completed_at = end_time
            deployment.deployment_time_seconds = int(deployment_time)
            self._update_status(deployment, DeploymentStatus.SUCCESS)
            
            self._log(deployment, f"🎉 Deployment completed in {deployment_time:.0f} seconds!", level="SUCCESS")
            
        except Exception as e:
            self._log(deployment, f"❌ Deployment failed: {str(e)}", level="ERROR")
            deployment.error_message = str(e)
            deployment.completed_at = datetime.utcnow()
            self._update_status(deployment, DeploymentStatus.FAILED)
        
        finally:
            # Clear log buffer after a delay to allow final streaming
            await asyncio.sleep(5)
            self.clear_log_buffer(deployment.id)
    
    
    async def cleanup_deployment(self, deployment_id: str):
        """Cleanup deployment resources"""
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        
        if not deployment or not deployment.instance:
            return
        
        try:
            # Destroy Terraform resources
            terraform_service = TerraformService(deployment.provider, deployment.region)
            await terraform_service.destroy(deployment_id)
            
            # Mark instance as destroyed
            deployment.instance.destroyed_at = datetime.utcnow()
            self.db.commit()
            
        except Exception as e:
            print(f"Error cleaning up deployment {deployment_id}: {e}")

    async def execute_redeployment(
        self,
        deployment_id: str,
        project: Project,
        github_token: str,
        existing_deployment: Deployment
    ):
        """Execute redeployment on existing infrastructure"""
        deployment = self.db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return
        
        print(f"[REDEPLOY] Starting redeployment for deployment {deployment_id}")
        print(f"[REDEPLOY] Existing deployment IP: {existing_deployment.public_ip}")
        print(f"[REDEPLOY] New deployment IP: {deployment.public_ip}")
        
        start_time = datetime.utcnow()
        
        try:
            # 1. Configure instance with Ansible (reuse existing infrastructure)
            self._log(deployment, "⚙️ Configuring instance...")
            self._update_status(deployment, DeploymentStatus.CONFIGURING)
            
            ansible_service = AnsibleService()
            await ansible_service.configure_instance(
                host=existing_deployment.public_ip,
                repo_url=f"https://github.com/{project.repo_full_name}.git",
                branch=deployment.branch,
                env_vars=deployment.env_vars,
                framework=project.framework,
                project_dir=None  # Let Ansible auto-detect
            )
            
            self._log(deployment, "✓ Instance configured successfully")
            
            # 2. Build application
            self._log(deployment, "🔨 Building application...")
            self._update_status(deployment, DeploymentStatus.BUILDING)
            
            await ansible_service.build_application(
                host=existing_deployment.public_ip,
                framework=project.framework,
                project_dir=None  # Let Ansible auto-detect
            )
            
            self._log(deployment, "✓ Application built successfully")
            
            # 3. Deploy application
            self._log(deployment, "🚀 Deploying application...")
            self._update_status(deployment, DeploymentStatus.DEPLOYING)
            
            app_url = await ansible_service.deploy_application(
                host=existing_deployment.public_ip,
                framework=project.framework,
                project_dir=None  # Let Ansible auto-detect
            )
            
            deployment.public_url = app_url or f"http://{existing_deployment.public_ip}"
            self.db.commit()
            
            self._log(deployment, f"✓ Application deployed: {deployment.public_url}")
            
            # 4. Complete deployment
            end_time = datetime.utcnow()
            deployment_time = (end_time - start_time).total_seconds()
            
            deployment.completed_at = end_time
            deployment.deployment_time_seconds = int(deployment_time)
            self._update_status(deployment, DeploymentStatus.SUCCESS)
            
            self._log(deployment, f"🎉 Redeployment completed in {deployment_time:.0f} seconds!")
            
        except Exception as e:
            self._log(deployment, f"❌ Redeployment failed: {str(e)}")
            deployment.error_message = str(e)
            deployment.completed_at = datetime.utcnow()
            self._update_status(deployment, DeploymentStatus.FAILED)
        
        finally:
            # No cleanup needed - Ansible handles everything on the instance
            pass