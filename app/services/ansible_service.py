import os
import tempfile
import asyncio
from typing import Dict, Callable, Optional
from ..config import settings

class AnsibleService:
    def __init__(self):
        self.ansible_bin = settings.ANSIBLE_PATH
        self.playbook_dir = "ansible"
    
    async def configure_instance(
        self,
        host: str,
        repo_url: str,
        branch: str,
        env_vars: Dict,
        framework: str,
        project_dir: str = None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """Configure instance with Ansible and retry logic"""
        max_retries = 3  # Reduced from 5 since we now wait for SSH first
        retry_delay = 10  # Reduced from 30 seconds
        
        if log_callback:
            log_callback(f"Starting instance configuration for {host}")
        
        for attempt in range(max_retries):
            try:
                if log_callback:
                    log_callback(f"Configuration attempt {attempt + 1}/{max_retries}")
                
                await self._run_playbook(
                    "configure.yml",
                    host,
                    extra_vars={
                        "repo_url": repo_url,
                        "branch": branch,
                        "env_vars": env_vars,
                        "framework": framework,
                        "project_dir": project_dir
                    },
                    log_callback=log_callback
                )
                
                if log_callback:
                    log_callback("Instance configuration completed successfully")
                return  # Success, exit the retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    error_msg = f"Configuration attempt {attempt + 1} failed, retrying in {retry_delay} seconds: {e}"
                    print(error_msg)
                    if log_callback:
                        log_callback(error_msg)
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Gentler exponential backoff
                else:
                    if log_callback:
                        log_callback(f"Configuration failed after {max_retries} attempts: {e}")
                    raise e  # Re-raise the exception on final attempt
    
    async def build_application(self, host: str, framework: str, project_dir: str = None, log_callback: Optional[Callable[[str], None]] = None):
        """Build application on instance with retry logic"""
        max_retries = 3
        retry_delay = 15
        
        if log_callback:
            log_callback(f"Starting application build for {framework} framework")
        
        for attempt in range(max_retries):
            try:
                if log_callback:
                    log_callback(f"Build attempt {attempt + 1}/{max_retries}")
                
                await self._run_playbook(
                    "build.yml",
                    host,
                    extra_vars={"framework": framework, "project_dir": project_dir},
                    log_callback=log_callback
                )
                
                if log_callback:
                    log_callback("Application build completed successfully")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    error_msg = f"Build attempt {attempt + 1} failed, retrying in {retry_delay} seconds: {e}"
                    print(error_msg)
                    if log_callback:
                        log_callback(error_msg)
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    if log_callback:
                        log_callback(f"Build failed after {max_retries} attempts: {e}")
                    raise e
    
    async def deploy_application(self, host: str, framework: str, project_dir: str = None, log_callback: Optional[Callable[[str], None]] = None) -> str:
        """Deploy application with retry logic"""
        max_retries = 3
        retry_delay = 15
        
        if log_callback:
            log_callback(f"Starting application deployment for {framework}")
        
        for attempt in range(max_retries):
            try:
                if log_callback:
                    log_callback(f"Deploy attempt {attempt + 1}/{max_retries}")
                
                await self._run_playbook(
                    "deploy.yml",
                    host,
                    extra_vars={"framework": framework, "project_dir": project_dir},
                    log_callback=log_callback
                )
                
                if log_callback:
                    log_callback(f"Application deployed successfully at http://{host}")
                return f"http://{host}"
            except Exception as e:
                if attempt < max_retries - 1:
                    error_msg = f"Deploy attempt {attempt + 1} failed, retrying in {retry_delay} seconds: {e}"
                    print(error_msg)
                    if log_callback:
                        log_callback(error_msg)
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    if log_callback:
                        log_callback(f"Deployment failed after {max_retries} attempts: {e}")
                    raise e
    
    async def _run_playbook(self, playbook: str, host: str, extra_vars: Dict = None, log_callback: Optional[Callable[[str], None]] = None):
        """Run Ansible playbook with verbose logging"""
        # For GCP instances, use the SSH key we generated
        inventory_content = f"""[web]
{host} ansible_user=ubuntu ansible_ssh_private_key_file=/tmp/deploy_key ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null' ansible_python_interpreter=/usr/bin/python3

[web:vars]
ansible_python_interpreter=/usr/bin/python3
"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ini') as inv_file:
            inv_file.write(inventory_content)
            inventory_path = inv_file.name
        
        try:
            cmd = [
                self.ansible_bin,
                "-i", inventory_path,
                os.path.join(self.playbook_dir, playbook),
                "-vvv"  # Use very verbose output for detailed logging
            ]
            
            if extra_vars:
                import json
                cmd.extend(["--extra-vars", json.dumps(extra_vars)])
            
            cmd_str = ' '.join(cmd)
            print(f"Running Ansible command: {cmd_str}")
            if log_callback:
                log_callback(f"Executing: ansible-playbook {playbook}")
            
            try:
                # Try async approach first
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )
                
                # Stream output in real-time
                output_lines = []
                async for line in process.stdout:
                    line = line.decode('utf-8').strip()
                    if line:
                        output_lines.append(line)
                        print(f"Ansible: {line}")
                        if log_callback:
                            log_callback(f"Ansible: {line}")
                
                await process.wait()
                full_output = '\n'.join(output_lines)
                return_code = process.returncode
                
            except Exception as async_error:
                # Fallback to synchronous execution if async fails
                print(f"Async execution failed, falling back to sync: {async_error}")
                if log_callback:
                    log_callback(f"Falling back to synchronous execution due to: {async_error}")
                
                import subprocess
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                full_output = result.stdout + result.stderr
                return_code = result.returncode
                
                # Log the output line by line for consistency
                for line in full_output.split('\n'):
                    line = line.strip()
                    if line:
                        print(f"Ansible: {line}")
                        if log_callback:
                            log_callback(f"Ansible: {line}")
            
            if return_code != 0:
                error_msg = f"Ansible failed with return code {return_code}"
                print(error_msg)
                print(f"Full output: {full_output}")
                if log_callback:
                    log_callback(error_msg)
                    log_callback(f"Detailed output: {full_output}")
                raise Exception(f"{error_msg}\nOutput: {full_output}")
            
            if log_callback:
                log_callback(f"Ansible playbook {playbook} completed successfully")
            
            return full_output
            
        finally:
            os.unlink(inventory_path)