#!/bin/bash
# Create a new database migration

if [ -z "$1" ]; then
    echo "Usage: ./create_migration.sh 'migration message'"
    exit 1
fi

alembic revision --autogenerate -m "$1"