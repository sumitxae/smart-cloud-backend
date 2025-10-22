import httpx
from typing import Dict, Optional

class GitLabService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://gitlab.com/api/v4"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
    
    async def get_repo_info(self, repo_full_name: str) -> Dict:
        """Get repository information"""
        # First, find the project by name
        async with httpx.AsyncClient() as client:
            # Search for the project
            search_response = await client.get(
                f"{self.base_url}/projects",
                headers=self.headers,
                params={
                    "search": repo_full_name.split('/')[-1],  # Search by repo name
                    "membership": "true"
                }
            )
            search_response.raise_for_status()
            projects = search_response.json()
            
            # Find exact match
            for project in projects:
                if project['path_with_namespace'] == repo_full_name:
                    return project
            
            raise Exception(f"Repository {repo_full_name} not found")
    
    async def get_repo_contents(self, repo_full_name: str, path: str = "") -> Dict:
        """Get repository contents at path"""
        project_id = await self._get_project_id(repo_full_name)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/projects/{project_id}/repository/tree",
                headers=self.headers,
                params={"path": path} if path else {}
            )
            response.raise_for_status()
            return response.json()
    
    async def check_file_exists(self, repo_full_name: str, filename: str, branch: str = "main") -> bool:
        """Check if a file exists in the repository"""
        try:
            project_id = await self._get_project_id(repo_full_name)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/projects/{project_id}/repository/files/{filename}",
                    headers=self.headers,
                    params={"ref": branch}
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def detect_framework(self, repo_full_name: str) -> Optional[str]:
        """Detect framework from repository files"""
        try:
            # Check for common framework files
            framework_files = {
                "package.json": "Node.js",
                "requirements.txt": "Python",
                "pom.xml": "Java",
                "composer.json": "PHP",
                "Gemfile": "Ruby",
                "Cargo.toml": "Rust",
                "go.mod": "Go"
            }
            
            for file, framework in framework_files.items():
                if await self.check_file_exists(repo_full_name, file):
                    return framework
            
            # Check for specific framework indicators
            if await self.check_file_exists(repo_full_name, "next.config.js"):
                return "Next.js"
            elif await self.check_file_exists(repo_full_name, "nuxt.config.js"):
                return "Nuxt.js"
            elif await self.check_file_exists(repo_full_name, "vue.config.js"):
                return "Vue.js"
            elif await self.check_file_exists(repo_full_name, "angular.json"):
                return "Angular"
            elif await self.check_file_exists(repo_full_name, "svelte.config.js"):
                return "Svelte"
            elif await self.check_file_exists(repo_full_name, "django_project"):
                return "Django"
            elif await self.check_file_exists(repo_full_name, "flask_app.py"):
                return "Flask"
            elif await self.check_file_exists(repo_full_name, "rails_app"):
                return "Rails"
            
            return "Unknown"
        except Exception:
            return "Unknown"
    
    async def get_file_content(self, repo_full_name: str, file_path: str) -> str:
        """Get file content from repository"""
        project_id = await self._get_project_id(repo_full_name)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/projects/{project_id}/repository/files/{file_path}",
                headers=self.headers,
                params={"ref": "main"}
            )
            response.raise_for_status()
            data = response.json()
            
            # Decode base64 content
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
    
    async def list_branches(self, repo_full_name: str) -> list:
        """List repository branches"""
        project_id = await self._get_project_id(repo_full_name)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/projects/{project_id}/repository/branches",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def _get_project_id(self, repo_full_name: str) -> str:
        """Get project ID from repository full name"""
        async with httpx.AsyncClient() as client:
            # Search for the project
            search_response = await client.get(
                f"{self.base_url}/projects",
                headers=self.headers,
                params={
                    "search": repo_full_name.split('/')[-1],  # Search by repo name
                    "membership": "true"
                }
            )
            search_response.raise_for_status()
            projects = search_response.json()
            
            # Find exact match
            for project in projects:
                if project['path_with_namespace'] == repo_full_name:
                    return str(project['id'])
            
            raise Exception(f"Repository {repo_full_name} not found")
