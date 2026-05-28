#!/usr/bin/env bash
set -o errexit

# Prefer binary wheels to avoid compiling from source
pip install --prefer-binary -r requirements.txt

# Run migrations against Supabase PostgreSQL
alembic upgrade head

# Create uploads directory
mkdir -p /tmp/uploads
