---
name: deploy
description: >-
  Build, test, and deploy the Autonomous Multi-Agent System containers to local Docker Compose, Google Cloud Run, and Streamlit Community Cloud with persistent SQLite storage.
---

# MAS Deployment Skill

Use this skill when deploying or testing containerized instances of the Autonomous Multi-Agent System.

## 1. Local Docker Compose Deployment
1. Verify `.env` contains a valid `GEMINI_API_KEY`.
2. Build and launch containers in detached mode:
   ```bash
   docker compose up --build -d
   ```
3. Check container health status:
   ```bash
   docker compose ps
   curl -f http://localhost:8000/api/system/status
   ```
4. Access the visual dashboard at `http://localhost:8501`.

## 2. Zero-Cost Cloud Run Deployment (Backend)
1. Submit build to Google Artifact Registry:
   ```bash
   gcloud builds submit --tag gcr.io/$PROJECT_ID/mas-backend -f backend/Dockerfile .
   ```
2. Deploy to Cloud Run mounting persistent GCS bucket:
   ```bash
   gcloud run deploy mas-backend \
     --image gcr.io/$PROJECT_ID/mas-backend \
     --region us-central1 \
     --add-volume=name=sqlite-vol,type=cloud-storage,bucket=mas-data-$PROJECT_ID \
     --add-volume-mount=volume=sqlite-vol,mount-path=/app/data
   ```

## 3. Streamlit Community Cloud Deployment (Frontend)
1. Push repository to GitHub.
2. Link repo in Streamlit Community Cloud with main path `frontend/app.py`.
3. Set secret `BACKEND_API_URL = "https://your-cloud-run-url.a.run.app"`.

## 4. Automated DevOps Scripts & GitHub Actions CI/CD
1. **Pre-flight Secret Check**:
   ```bash
   python3 scripts/validate_secrets.py
   ```
2. **Deploy to Staging**:
   ```bash
   bash scripts/deploy_staging.sh
   # Or push to feature/* to trigger .github/workflows/deploy-staging.yml
   ```
3. **Deploy to Production**:
   ```bash
   bash scripts/deploy_prod.sh
   # Or create release tag (v*.*.*) to trigger .github/workflows/deploy-prod.yml
   ```

