#!/bin/bash
# Setup script for Smart Cloud Deploy backend

set -e

echo "🚀 Setting up Smart Cloud Deploy Backend..."

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed."; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "⚠️  Terraform not found. Install from https://terraform.io"; }
command -v ansible >/dev/null 2>&1 || { echo "⚠️  Ansible not found. Will be installed via pip."; }

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy environment file
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "⚠️  Please update .env with your credentials!"
fi

# Setup database
echo "🗄️  Setting up database..."
docker-compose up -d db redis

# Wait for database
echo "⏳ Waiting for database to be ready..."
sleep 5

# Run migrations
echo "🔄 Running database migrations..."
alembic upgrade head

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env with your credentials (GitHub OAuth, AWS, GCP)"
echo "2. Start the API: make dev"
echo "3. Or use Docker: make docker-up"
echo "4. Visit http://localhost:8000/docs for API documentation" 