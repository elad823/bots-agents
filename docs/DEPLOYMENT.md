# Infrastructure & Deployment Strategy
## Project: Autonomous Multi-Agent System (MAS) & Visual Control Plane

### 1. Zero-Cost Production Topology Overview

The system is architected for zero-cost, enterprise-grade cloud hosting utilizing free-tier allowances without running costly persistent virtual machines:

```mermaid
graph LR
    subgraph StreamlitCloud ["Streamlit Community Cloud (Frontend)"]
        UI["Streamlit Dashboard (Zero Cost)"]
    end

    subgraph GoogleCloud ["Google Cloud Run (Backend & Agents)"]
        FastAPI["FastAPI App + LangGraph Engine (Free Tier)"]
        Scheduler["APScheduler Background Service"]
        FastAPI --- Scheduler
    end

    subgraph Storage ["Persistent Storage"]
        GCS["Cloud Storage Bucket (GCS FUSE Volume) or Litestream"]
        DB[("mas_database.db")]
        GCS --- DB
    end

    subgraph LLM ["Google AI Studio"]
        Gemini["Gemini 1.5 Flash / Pro (Free Tier 15 RPM)"]
    end

    UI -->|HTTPS REST| FastAPI
    FastAPI -->|Direct Volume I/O| DB
    FastAPI -->|Tenacity + Rate Limiter| Gemini
```

#### Cost Profile
- **Google Cloud Run (Backend)**: Free Tier includes 2 million requests/month, 360,000 vCPU-seconds, and 180,000 GiB-seconds memory. Configured with `--min-instances=0` (or `1` during active scheduling) and `--memory=1Gi`.
- **Streamlit Community Cloud (Frontend)**: 100% Free public hosting directly connected to GitHub repository.
- **Google Cloud Storage (SQLite Persistence)**: Free Tier includes 5 GB standard storage per month. Mounted as a Cloud Run Second Gen volume via Cloud Storage FUSE, giving the SQLite database atomic persistence across container revisions and cold starts.
- **Google AI Studio**: Free-tier Gemini 1.5 Flash API keys (15 RPM).

---

### 2. Local Docker & Docker Compose Specification

#### 2.1. Backend Container (`backend/Dockerfile`)
```dockerfile
# Multi-stage lean Python 3.11 build
FROM python:3.11-slim as base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (sqlite3, curl for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source code and initial data directory
COPY backend/ ./backend/
RUN mkdir -p /app/data

# Expose FastAPI port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/status || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 2.2. Frontend Container (`frontend/Dockerfile`)
```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir streamlit httpx pydantic

COPY frontend/ ./frontend/

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "frontend/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### 2.3. Local Orchestration (`docker-compose.yml`)
```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: mas_backend
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - DATABASE_PATH=/app/data/mas_database.db
      - ENVIRONMENT=development
      - LOG_LEVEL=INFO
      - CORS_ORIGINS=http://localhost:8501,http://frontend:8501
    volumes:
      # Persistent named volume for SQLite database and task logs
      - mas_sqlite_data:/app/data
      # Bind mount code for hot reloading during development
      - ./backend:/app/backend
    restart: unless-stopped
    networks:
      - mas_network

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    container_name: mas_frontend
    ports:
      - "8501:8501"
    environment:
      - BACKEND_API_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    volumes:
      - ./frontend:/app/frontend
    restart: unless-stopped
    networks:
      - mas_network

volumes:
  mas_sqlite_data:
    name: mas_sqlite_data
    driver: local

networks:
  mas_network:
    name: mas_network
    driver: bridge
```

---

### 3. Persistent Storage Strategy for SQLite

SQLite requires atomic filesystem locking. To avoid database loss during container restarts and redeployments:

1. **Local Development (Docker Compose)**:
   - Configured with a dedicated named volume `mas_sqlite_data` mounted to `/app/data`.
   - Data persists across `docker-compose down` and `docker-compose up`.
2. **Google Cloud Run (Production)**:
   - **Method A (Cloud Storage Volume Mount - Recommended)**:
     - Cloud Run supports mounting a Google Cloud Storage (GCS) bucket directly as a filesystem directory via Cloud Storage FUSE.
     - Deploy with: `--add-volume=name=db-storage,type=cloud-storage,bucket=YOUR_GCS_BUCKET --add-volume-mount=volume=db-storage,mount-path=/app/data`.
   - **Method B (Litestream Continuous Replication - Alternative Zero-Cost Option)**:
     - Runs a lightweight background daemon inside the container that streams SQLite WAL changes to a free GCS bucket in real-time and restores the database on container initialization.

---

### 4. Environment Variables & Secret Management

#### 4.1. `.env.example` Template
```ini
# ==============================================================================
# Autonomous Multi-Agent System (MAS) Environment Configuration
# ==============================================================================

# LLM Provider Configuration
GEMINI_API_KEY=your_google_ai_studio_api_key_here
GEMINI_MODEL_DEFAULT=gemini-1.5-flash

# Backend & Database Configuration
ENVIRONMENT=development
PORT=8000
DATABASE_PATH=data/mas_database.db
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:8501,http://localhost:3000

# Rate Limiter Guardrails (Google AI Studio Free Tier is 15 RPM)
MAX_RPM_LIMIT=14
RATE_LIMIT_WINDOW_SECONDS=60

# Frontend Configuration
BACKEND_API_URL=http://localhost:8000
STREAMLIT_SERVER_PORT=8501
```

#### 4.2. Secret Security Rules
- `.env` and `data/*.db` are strictly listed in `.gitignore`.
- On Cloud Run: Inject `GEMINI_API_KEY` via Google Secret Manager or direct environment variables.
- On Streamlit Cloud: Configure `BACKEND_API_URL` under **App Settings > Secrets**.

---

### 5. Step-by-Step Zero-Cost Deployment Guide

#### Step 5.1: Local Orchestration with Docker
1. Clone the repository and configure `.env`:
   ```bash
   cp .env.example .env
   # Edit .env and set GEMINI_API_KEY
   ```
2. Build and launch with Docker Compose:
   ```bash
   docker compose up --build -d
   ```
3. Verify running containers:
   - FastAPI API: `http://localhost:8000/docs`
   - Streamlit Dashboard: `http://localhost:8501`
4. Inspect database persistence:
   ```bash
   docker compose exec backend sqlite3 /app/data/mas_database.db "SELECT * FROM agents;"
   ```

#### Step 5.2: Deploying FastAPI Backend to Google Cloud Run
1. Authenticate with Google Cloud SDK:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_GCP_PROJECT_ID
   ```
2. Create a persistent GCS bucket for SQLite data (free tier 5GB):
   ```bash
   gcloud storage buckets create gs://mas-data-YOUR_PROJECT_ID --location=us-central1
   ```
3. Build and push the backend container to Google Artifact Registry:
   ```bash
   gcloud builds submit --tag gcr.io/YOUR_GCP_PROJECT_ID/mas-backend -f backend/Dockerfile .
   ```
4. Deploy to Cloud Run with GCS volume mount:
   ```bash
   gcloud run deploy mas-backend \
     --image gcr.io/YOUR_GCP_PROJECT_ID/mas-backend \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars="GEMINI_API_KEY=YOUR_KEY,DATABASE_PATH=/app/data/mas_database.db,MAX_RPM_LIMIT=14" \
     --execution-environment gen2 \
     --add-volume=name=sqlite-vol,type=cloud-storage,bucket=mas-data-YOUR_PROJECT_ID \
     --add-volume-mount=volume=sqlite-vol,mount-path=/app/data
   ```
5. Capture your deployed backend URL: `https://mas-backend-xyz.a.run.app`.

#### Step 5.3: Deploying Frontend to Streamlit Community Cloud
1. Push your repository to GitHub (main branch or dedicated branch).
2. Go to [share.streamlit.io](https://share.streamlit.io/) and create a new application.
3. Select your repository, set the App path to `frontend/app.py`.
4. Under **Advanced Settings -> Secrets**, add:
   ```toml
   BACKEND_API_URL = "https://mas-backend-xyz.a.run.app"
   ```
5. Click **Deploy**. Your visual MAS control plane is live with zero monthly hosting cost.
