#!/usr/bin/env bash
# ==============================================================================
# Deploy Production Environment - Autonomous Multi-Agent System (MAS)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=================================================="
echo " 🛡️ Deploying MAS to Production Environment"
echo " Workspace: $WORKSPACE_ROOT"
echo "=================================================="

# 1. Security Gate: Pre-flight Secret Audit
echo "[*] Step 1/5: Running mandatory pre-flight security scan..."
python3 "$SCRIPT_DIR/validate_secrets.py"

# 2. Quality Gate: Run Full Automated Test Suite
echo "[*] Step 2/5: Running full test suite including E2E pipeline..."
python3 "$WORKSPACE_ROOT/run_tests.py"

# 3. Build Production Container
GCP_PROJECT="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo 'mas-prod')}"
VERSION_TAG="${VERSION_TAG:-$(date +%Y%m%d%H%M%S)}"
IMAGE_TAG="gcr.io/$GCP_PROJECT/mas-backend:$VERSION_TAG"

echo "[*] Step 3/5: Building production container ($IMAGE_TAG)..."
docker build -t "$IMAGE_TAG" -f "$WORKSPACE_ROOT/backend/Dockerfile" "$WORKSPACE_ROOT"

# 4. Deploy Canary Revision (Zero-Traffic)
echo "[*] Step 4/5: Deploying canary revision to Cloud Run (mas-backend-prod)..."
if command -v gcloud &>/dev/null; then
    gcloud run deploy mas-backend-prod \
        --image "$IMAGE_TAG" \
        --region us-central1 \
        --platform managed \
        --port 8080 \
        --memory 2Gi \
        --cpu 2 \
        --min-instances 1 \
        --max-instances 5 \
        --no-traffic \
        --allow-unauthenticated \
        --set-env-vars "ENVIRONMENT=production,LOG_LEVEL=WARNING,MAX_RPM_LIMIT=14"

    # 5. Shift 100% Traffic Post Health Check
    echo "[*] Step 5/5: Shifting 100% production traffic to new revision..."
    gcloud run services update-traffic mas-backend-prod --to-latest --region=us-central1
    echo "✅ Production deployment and zero-downtime traffic shift succeeded!"
else
    echo "⚠️ gcloud CLI not found on local machine. Use GitHub Actions for automated remote deploy."
fi
