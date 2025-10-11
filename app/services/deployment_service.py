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
            
            # Use a separate session for logging to avoid blocking
            try:
                # Quick commit with short timeout
                self.db.commit()
            except Exception as e:
                print(f"Warning: Failed to log message: {e}")
                # Don't fail the deployment just because logging failed
                pass
    
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
    
    async def _wait_for_instance_boot(self, deployment: Deployment, host: str, initial_wait: int = 60):
        """Wait for instance to fully boot before attempting SSH connections"""
        self._log(deployment, f"⏰ Instance created, waiting {initial_wait} seconds for full boot...")
        self._log_verbose(deployment, "This initial wait ensures the instance is fully booted before SSH attempts")
        
        # Initial wait for instance to boot
        await asyncio.sleep(initial_wait)
        
        # Additional checks to ensure instance is responding
        self._log(deployment, "🔍 Verifying instance is responding...")
        
        # Check if instance is responding to ping (basic connectivity)
        for attempt in range(1, 6):  # 5 attempts over 30 seconds
            try:
                self._log_verbose(deployment, f"Ping check attempt {attempt}/5")
                
                # Use ping command to check basic connectivity
                ping_cmd = ["ping", "-c", "1", "-W", "5", host]  # 5 second timeout
                result = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    self._log(deployment, f"✓ Instance is responding to ping")
                    return
                else:
                    self._log_verbose(deployment, f"Ping failed (attempt {attempt}): {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                self._log_verbose(deployment, f"Ping timeout (attempt {attempt})")
            except Exception as e:
                self._log_verbose(deployment, f"Ping error (attempt {attempt}): {e}")
            
            if attempt < 5:
                self._log_verbose(deployment, f"Waiting 6 seconds before next ping attempt...")
                await asyncio.sleep(6)
        
        # Even if ping fails, continue - SSH might still work
        self._log(deployment, "⚠️ Ping checks failed, but proceeding with SSH connection attempt")
        self._log_verbose(deployment, "This is normal for some cloud providers - SSH may still work")
    
    async def _wait_for_ssh_ready(self, deployment: Deployment, host: str, port: int = 22, timeout: int = 180):
        """Wait for SSH to be ready on the instance with detailed diagnostics"""
        self._log(deployment, f"🔐 Checking SSH connectivity to {host}:{port}")
        self._log_verbose(deployment, "SSH connection diagnostics will help identify any issues")
        
        start_time = datetime.utcnow()
        attempt = 0
        max_attempts = 20  # Increased attempts since we now wait for boot first
        
        # First, check if SSH key exists
        import os
        if not os.path.exists("/tmp/deploy_key"):
            self._log(deployment, "❌ SSH key not found at /tmp/deploy_key")
            raise Exception("SSH key not found - cannot proceed with SSH connection")
        
        self._log_verbose(deployment, "✓ SSH key found at /tmp/deploy_key")
        
        while attempt < max_attempts and (datetime.utcnow() - start_time).total_seconds() < timeout:
            attempt += 1
            try:
                self._log_verbose(deployment, f"SSH check attempt {attempt}/{max_attempts}")
                
                # Step 1: Check if SSH port is open
                self._log_verbose(deployment, f"Checking if SSH port {port} is open...")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)  # Slightly longer timeout for port check
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    self._log(deployment, f"✓ SSH port {port} is open on {host}")
                    
                    # Step 2: Test SSH authentication
                    self._log_verbose(deployment, f"Testing SSH authentication...")
                    try:
                        ssh_test_cmd = [
                            "timeout", "10",  # 10 second timeout for SSH test
                            "ssh", 
                            "-i", "/tmp/deploy_key",
                            "-o", "StrictHostKeyChecking=no",
                            "-o", "UserKnownHostsFile=/dev/null",
                            "-o", "ConnectTimeout=5",
                            "-o", "BatchMode=yes",
                            "-o", "LogLevel=ERROR",  # Reduce SSH verbosity
                            f"ubuntu@{host}",
                            "echo 'SSH_AUTH_SUCCESS'"
                        ]
                        
                        self._log_verbose(deployment, f"Running SSH test: {' '.join(ssh_test_cmd)}")
                        
                        # Run SSH test asynchronously
                        process = await asyncio.create_subprocess_exec(
                            *ssh_test_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        
                        try:
                            stdout, stderr = await asyncio.wait_for(
                                process.communicate(), 
                                timeout=15  # 15 second total timeout
                            )
                            
                            stdout_str = stdout.decode('utf-8').strip()
                            stderr_str = stderr.decode('utf-8').strip()
                            
                            if process.returncode == 0 and 'SSH_AUTH_SUCCESS' in stdout_str:
                                self._log(deployment, f"✓ SSH authentication successful to {host}")
                                self._log_verbose(deployment, f"SSH response: {stdout_str}")
                                return
                            else:
                                self._log_verbose(deployment, f"SSH auth failed (attempt {attempt})")
                                self._log_verbose(deployment, f"SSH stdout: {stdout_str}")
                                self._log_verbose(deployment, f"SSH stderr: {stderr_str}")
                                self._log_verbose(deployment, f"SSH return code: {process.returncode}")
                                
                        except asyncio.TimeoutError:
                            process.kill()
                            self._log_verbose(deployment, f"SSH test timed out after 15 seconds (attempt {attempt})")
                            
                    except Exception as e:
                        self._log_verbose(deployment, f"SSH test error (attempt {attempt}): {e}")
                        
                else:
                    # Port is not open - provide detailed error info
                    error_codes = {
                        35: "Network unreachable",
                        61: "Connection refused (SSH service not running)",
                        110: "Connection timed out",
                        111: "Connection refused (port not open)"
                    }
                    error_msg = error_codes.get(result, f"Unknown error code: {result}")
                    self._log_verbose(deployment, f"SSH port not ready: {error_msg} (code {result}, attempt {attempt})")
                    
            except Exception as e:
                self._log_verbose(deployment, f"Connection check error (attempt {attempt}): {e}")
            
            # Progressive wait times - longer waits for later attempts
            if attempt <= 3:
                wait_time = 5  # First 3 attempts wait 5 seconds
            elif attempt <= 8:
                wait_time = 10  # Next 5 attempts wait 10 seconds
            else:
                wait_time = 15  # Later attempts wait 15 seconds
                
            self._log_verbose(deployment, f"Waiting {wait_time}s before next attempt...")
            await asyncio.sleep(wait_time)
        
        # Provide detailed failure information
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        self._log(deployment, f"⚠️ SSH readiness check completed after {attempt} attempts ({elapsed_time:.1f}s)")
        self._log_verbose(deployment, "Proceeding with Ansible configuration - it has its own SSH retry logic")
        self._log_verbose(deployment, "Common SSH issues: instance still booting, firewall rules, SSH key permissions")
    
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
            await self._wait_for_instance_boot(deployment, instance_info["public_ip"])
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