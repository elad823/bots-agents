#!/usr/bin/env bash
# ==============================================================================
# Deploy Staging Environment - Autonomous Multi-Agent System (MAS)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=================================================="
echo " 🚀 Deploying MAS to Staging Environment"
echo " Workspace: $WORKSPACE_ROOT"
echo "=================================================="

# 1. Pre-flight Secret & Vulnerability Scan
echo "[*] Step 1/4: Running pre-flight security scan..."
python3 "$SCRIPT_DIR/validate_secrets.py"

# 2. Run All Unit, Integration, & E2E Tests
echo "[*] Step 2/4: Running test suite..."
python3 "$WORKSPACE_ROOT/run_tests.py"

# 3. Build Staging Docker Image
GCP_PROJECT="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo 'mas-staging')}"
IMAGE_TAG="gcr.io/$GCP_PROJECT/mas-backend:staging-latest"

echo "[*] Step 3/4: Building staging container ($IMAGE_TAG)..."
docker build -t "$IMAGE_TAG" -f "$WORKSPACE_ROOT/backend/Dockerfile" "$WORKSPACE_ROOT"

# 4. Deploy to Google Cloud Run (Staging)
echo "[*] Step 4/4: Deploying to Google Cloud Run (mas-backend-staging)..."
if command -v gcloud &>/dev/null; then
    gcloud run deploy mas-backend-staging \
        --image "$IMAGE_TAG" \
        --region us-central1 \
        --platform managed \
        --port 8080 \
        --memory 1Gi \
        --cpu 1 \
        --min-instances 0 \
        --max-instances 2 \
        --allow-unauthenticated \
        --set-env-vars "ENVIRONMENT=staging,LOG_LEVEL=INFO,MAX_RPM_LIMIT=14"
    echo "✅ Staging deployment completed successfully!"
else
    echo "⚠️ gcloud CLI not found on local machine. Use GitHub Actions for automated remote deploy."
fi
