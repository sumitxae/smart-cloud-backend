import httpx
from typing import Dict, Optional

class GitHubService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    async def get_repo_info(self, repo_full_name: str) -> Dict:
        """Get repository information"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{repo_full_name}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_repo_contents(self, repo_full_name: str, path: str = "") -> Dict:
        """Get repository contents at path"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{repo_full_name}/contents/{path}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def check_file_exists(self, repo_full_name: str, filename: str, branch: str = "main") -> bool:
        """Check if a file exists in the repository"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/repos/{repo_full_name}/contents/{filename}?ref={branch}",
                    headers=self.headers
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def detect_framework(self, repo_full_name: str) -> Optional[str]:
        """Detect project framework from repository files"""
        try:
            contents = await self.get_repo_contents(repo_full_name)
            
            # Check for common framework indicators
            files = [item["name"] for item in contents if item["type"] == "file"]
            
            # React / Node.js
            if "package.json" in files:
                package_json = await self.get_file_content(repo_full_name, "package.json")
                if "react" in package_json.lower():
                    return "React"
                elif "vue" in package_json.lower():
                    return "Vue"
                elif "next" in package_json.lower():
                    return "Next.js"
                elif "angular" in package_json.lower():
                    return "Angular"
                return "Node.js"
            
            # Python
            if "requirements.txt" in files or "pyproject.toml" in files:
                if "manage.py" in files:
                    return "Django"
                elif "app.py" in files or "main.py" in files:
                    return "Flask/FastAPI"
                return "Python"
            
            # Go
            if "go.mod" in files:
                return "Go"
            
            # Java
            if "pom.xml" in files:
                return "Maven/Java"
            
            # Ruby
            if "Gemfile" in files:
                return "Ruby/Rails"
            
            return "Unknown"
        except Exception:
            return "Unknown"
    
    async def get_file_content(self, repo_full_name: str, file_path: str) -> str:
        """Get file content from repository"""
        import base64
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{repo_full_name}/contents/{file_path}",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            # Decode base64 content
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
    
    async def list_branches(self, repo_full_name: str) -> list:
        """List repository branches"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/repos/{repo_full_name}/branches",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
