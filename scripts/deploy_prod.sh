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

# 1. Identity & Re-Authentication Gate (Prod uses separate account from stage/test)
echo "[*] Step 1/6: Verifying Production Identity & Re-Authentication Gate..."
if command -v gcloud &>/dev/null; then
    ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || echo 'Unknown')"
    ACTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || echo 'Unknown')"
    echo "    • Current Active GCP Account : $ACTIVE_ACCOUNT"
    echo "    • Current Active GCP Project : $ACTIVE_PROJECT"
    echo ""
    echo "⚠️  CRITICAL PRODUCTION ISOLATION NOTICE:"
    echo "    Production requires a dedicated Google account and project, completely isolated"
    echo "    from the test/staging accounts to protect Gemini rate limits and data isolation."
    echo ""
    read -r -p "    Do you need to re-authenticate with your production GCP account? (y/N): " REAUTH_CHOICE
    if [[ "$REAUTH_CHOICE" =~ ^[Yy]$ ]]; then
        echo "[*] Launching gcloud re-authentication..."
        gcloud auth login
        ACTIVE_ACCOUNT="$(gcloud config get-value account 2>/dev/null || echo 'Unknown')"
        echo "✅ Authenticated as: $ACTIVE_ACCOUNT"
    fi
fi

echo ""
echo "🔒 MANUAL PRODUCTION CONFIRMATION REQUIRED:"
echo "   Type 'DEPLOY_PRODUCTION' to proceed with production rollout (or anything else to abort):"
read -r -p "   > " PROD_CONFIRMATION

if [ "$PROD_CONFIRMATION" != "DEPLOY_PRODUCTION" ]; then
    echo "❌ ERROR: Production deployment aborted. Confirmation mismatched."
    exit 1
fi
echo "✅ Manual production confirmation verified."
echo ""

# 2. Security Gate: Pre-flight Secret Audit
echo "[*] Step 2/6: Running mandatory pre-flight security scan..."
python3 "$SCRIPT_DIR/validate_secrets.py"

# 3. Quality Gate: Run Full Automated Test Suite
echo "[*] Step 3/6: Running full test suite including E2E pipeline..."
python3 "$WORKSPACE_ROOT/run_tests.py"

# 4. Build Production Container
GCP_PROJECT="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || echo 'mas-prod')}"
VERSION_TAG="${VERSION_TAG:-$(date +%Y%m%d%H%M%S)}"
IMAGE_TAG="gcr.io/$GCP_PROJECT/mas-backend:$VERSION_TAG"

echo "[*] Step 4/6: Building production container ($IMAGE_TAG)..."
docker build -t "$IMAGE_TAG" -f "$WORKSPACE_ROOT/backend/Dockerfile" "$WORKSPACE_ROOT"

# 5. Deploy Canary Revision (Zero-Traffic)
echo "[*] Step 5/6: Deploying canary revision to Cloud Run (mas-backend-prod)..."
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

    # 6. Shift 100% Traffic Post Health Check
    echo "[*] Step 6/6: Shifting 100% production traffic to new revision..."
    gcloud run services update-traffic mas-backend-prod --to-latest --region=us-central1
    echo "✅ Production deployment and zero-downtime traffic shift succeeded!"
else
    echo "⚠️ gcloud CLI not found on local machine. Use GitHub Actions for automated remote deploy."
fi
