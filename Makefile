.PHONY: help install dev migrate upgrade test clean docker-build docker-up docker-down

help:
	@echo "Smart Cloud Deploy - Backend"
	@echo ""
	@echo "Available commands:"
	@echo "  make install       - Install dependencies"
	@echo "  make dev          - Run development server"
	@echo "  make migrate      - Create migration"
	@echo "  make upgrade      - Apply migrations"
	@echo "  make test         - Run tests"
	@echo "  make docker-build - Build Docker images"
	@echo "  make docker-up    - Start Docker containers"
	@echo "  make docker-down  - Stop Docker containers"
	@echo "  make clean        - Clean temporary files"

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic revision --autogenerate -m "$(msg)"

upgrade:
	alembic upgrade head

test:
	pytest tests/ -v

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf /tmp/deployments/*
