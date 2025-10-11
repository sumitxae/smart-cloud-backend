import os
from typing import Optional

def detect_framework_from_files(repo_path: str) -> Optional[str]:
    """Detect framework from local repository files"""
    
    files = os.listdir(repo_path)
    
    # React / Next.js / Vue / Angular
    if "package.json" in files:
        package_json_path = os.path.join(repo_path, "package.json")
        try:
            import json
            with open(package_json_path, 'r') as f:
                package = json.load(f)
                deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                
                if "next" in deps:
                    return "Next.js"
                elif "react" in deps:
                    return "React"
                elif "vue" in deps:
                    return "Vue"
                elif "@angular/core" in deps:
                    return "Angular"
                elif "express" in deps:
                    return "Express"
                return "Node.js"
        except:
            return "Node.js"
    
    # Python frameworks
    if "requirements.txt" in files or "pyproject.toml" in files:
        if "manage.py" in files:
            return "Django"
        
        # Check requirements.txt for framework
        if "requirements.txt" in files:
            req_path = os.path.join(repo_path, "requirements.txt")
            try:
                with open(req_path, 'r') as f:
                    content = f.read().lower()
                    if "django" in content:
                        return "Django"
                    elif "flask" in content:
                        return "Flask"
                    elif "fastapi" in content:
                        return "FastAPI"
            except:
                pass
        
        return "Python"
    
    # Go
    if "go.mod" in files:
        return "Go"
    
    # Java / Maven
    if "pom.xml" in files:
        return "Maven/Spring"
    
    # Java / Gradle
    if "build.gradle" in files or "build.gradle.kts" in files:
        return "Gradle/Spring"
    
    # Ruby / Rails
    if "Gemfile" in files:
        return "Ruby/Rails"
    
    # PHP / Laravel
    if "composer.json" in files:
        composer_path = os.path.join(repo_path, "composer.json")
        try:
            import json
            with open(composer_path, 'r') as f:
                composer = json.load(f)
                if "laravel/framework" in composer.get("require", {}):
                    return "Laravel"
        except:
            pass
        return "PHP"
    
    # Static sites
    if "index.html" in files:
        return "Static HTML"
    
    return "Unknown"

def generate_dockerfile(framework: str, port: int = None) -> str:
    """Generate Dockerfile based on framework"""
    
    dockerfiles = {
        "React": f"""FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY --from=build /app/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]""",

        "Next.js": f"""FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE {port or 3000}
CMD ["npm", "start"]""",

        "Node.js": f"""FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE {port or 3000}
CMD ["npm", "start"]""",

        "Python": f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port or 8000}
CMD ["python", "app.py"]""",

        "Django": f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
EXPOSE {port or 8000}
CMD ["gunicorn", "--bind", "0.0.0.0:{port or 8000}", "wsgi:application"]""",

        "Flask": f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port or 5000}
CMD ["gunicorn", "--bind", "0.0.0.0:{port or 5000}", "app:app"]""",

        "FastAPI": f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {port or 8000}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port or 8000}"]""",

        "Go": f"""FROM golang:1.21-alpine as build
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN go build -o main .

FROM alpine:latest
WORKDIR /root/
COPY --from=build /app/main .
EXPOSE {port or 8080}
CMD ["./main"]""",
    }
    
    return dockerfiles.get(framework, dockerfiles["Node.js"])