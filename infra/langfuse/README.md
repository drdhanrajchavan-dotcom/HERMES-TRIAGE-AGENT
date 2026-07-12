# Langfuse Wi-Fi fallback

This directory vendors the official Langfuse v3 self-host `docker-compose.yml` from the Langfuse repository.

## Start

1. Copy `.env.example` to `.env` inside this directory.
2. Generate every marked secret; do not reuse application secrets.
3. Run `docker compose up -d`.
4. Open `http://localhost:3000` and create/initialize the project.
5. Point the runner's `LANGFUSE_HOST` to `http://localhost:3000` and configure the generated project keys.

The compose file exposes only the Langfuse web and MinIO ingress publicly by default; database/cache ports bind to localhost. This is an event fallback, not the production deployment topology.
