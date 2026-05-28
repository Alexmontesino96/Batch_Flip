#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Run migrations against Supabase PostgreSQL
alembic upgrade head

# Create uploads directory
mkdir -p /tmp/uploads
