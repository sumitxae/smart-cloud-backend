FastAPI backend for automated cloud deployments with GitHub integration, Terraform provisioning, and Ansible configuration.

## Features

- 🔐 GitHub OAuth authentication
- 📦 Automatic repository detection and framework identification
- ☁️ Multi-cloud support (AWS, GCP, Azure)
- 🏗️ Infrastructure provisioning with Terraform
- ⚙️ Automated configuration with Ansible
- 📊 Real-time deployment logs via Server-Sent Events
- 🔄 Background task processing with Celery
- 💾 PostgreSQL database with SQLAlchemy ORM

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL
- Redis
- Terraform
- Ansible
- AWS/GCP credentials

### Installation

1. Clone the repository
2. Copy `.env.example` to `.env` and configure
3. Install dependencies:

```bash
make install
```

4. Start services with Docker:

```bash
make docker-up
```

5. Apply database migrations:

```bash
make upgrade
```

6. Access API documentation: http://localhost:8000/docs

## Environment Variables

See `.env.example` for all required configuration.

Key variables:
- `DATABASE_URL`: PostgreSQL connection string
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`: GitHub OAuth app credentials
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: AWS credentials
- `GCP_SERVICE_ACCOUNT_PATH`: Path to GCP service account JSON

## API Endpoints

### Authentication
- `GET /api/v1/auth/github/login` - Start GitHub OAuth flow
- `GET /api/v1/auth/github/callback` - OAuth callback
- `GET /api/v1/auth/me` - Get current user

### Projects
- `GET /api/v1/projects` - List projects
- `POST /api/v1/projects` - Create project
- `GET /api/v1/projects/{id}` - Get project
- `PUT /api/v1/projects/{id}` - Update project
- `DELETE /api/v1/projects/{id}` - Delete project

### Deployments
- `POST /api/v1/deployments/start` - Start deployment
- `GET /api/v1/deployments/{id}/status` - Get status
- `GET /api/v1/deployments/{id}/logs` - Stream logs (SSE)
- `GET /api/v1/deployments` - List deployments
- `DELETE /api/v1/deployments/{id}` - Delete deployment

### Cloud Providers
- `GET /api/v1/cloud/providers` - List providers
- `POST /api/v1/cloud/credentials` - Save credentials
- `POST /api/v1/cloud/estimate-cost` - Estimate costs

## Development

Run locally:
```bash
make dev
```

Create migration:
```bash
make migrate msg="your migration message"
```

Run tests:
```bash
make test
```

## Architecture

```
Frontend (React) 
    ↓
FastAPI Backend
    ↓
┌─────────┬──────────┬──────────┐
│ GitHub  │Terraform │ Ansible  │
│ Service │ Service  │ Service  │
└─────────┴──────────┴──────────┘
    ↓          ↓          ↓
Repository  Cloud VMs  Configuration
```

## License

MIT