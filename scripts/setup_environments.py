#!/usr/bin/env python3
"""Interactive Environment & Secret Configuration Wizard for MAS.

Configures:
1. Local Environment (.env)
2. Staging Environment (GitHub Secrets & Settings)
3. Production Environment (Enforces mandatory re-authentication and separate account verification)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = WORKSPACE_ROOT / ".env"
ENV_EXAMPLE = WORKSPACE_ROOT / ".env.example"


def run_cmd(cmd: list[str], capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute a shell command safely."""
    return subprocess.run(cmd, cwd=str(WORKSPACE_ROOT), text=True, capture_output=capture_output)


def check_gh_installed() -> bool:
    """Verify if gh CLI is installed and authenticated."""
    res = run_cmd(["which", "gh"])
    if res.returncode != 0:
        return False
    auth_res = run_cmd(["gh", "auth", "status"])
    return auth_res.returncode == 0


def set_github_secret(secret_name: str, secret_val: str, env_name: str) -> bool:
    """Set a secret in a specific GitHub Environment using gh CLI."""
    process = subprocess.Popen(
        ["gh", "secret", "set", secret_name, "--env", env_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(WORKSPACE_ROOT),
    )
    stdout, stderr = process.communicate(input=secret_val)
    if process.returncode != 0:
        print(f"❌ Failed to set GitHub secret {secret_name} in {env_name}: {stderr.strip()}")
        return False
    print(f"✅ Configured GitHub secret [{secret_name}] in [{env_name}] environment.")
    return True


def setup_local_env() -> None:
    """Configure local .env file."""
    print("\n==================================================")
    print(" 💻 Step 1: Configure Local Development (.env)")
    print("==================================================")
    print("This key will be stored locally in .env (ignored by git).")
    print("Use Account 1 (Test / Staging account).")

    key = input("Enter your Local Gemini API Key (or press Enter to keep 'mock_dev_key'): ").strip()
    if not key:
        key = "mock_dev_key"

    env_content = f"""# ==============================================================================
# Autonomous Multi-Agent System (MAS) Local Environment Configuration
# ==============================================================================
GEMINI_API_KEY={key}
GEMINI_MODEL_DEFAULT=gemini-1.5-flash
ENVIRONMENT=development
PORT=8000
DATABASE_PATH=data/mas_database.db
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:8501,http://frontend:8501
MAX_RPM_LIMIT=14
RATE_LIMIT_WINDOW_SECONDS=60
BACKEND_API_URL=http://localhost:8000
STREAMLIT_SERVER_PORT=8501
"""
    ENV_FILE.write_text(env_content, encoding="utf-8")
    print(f"✅ Local .env configured successfully at {ENV_FILE.relative_to(WORKSPACE_ROOT)}!")


def setup_staging_env(gh_ready: bool) -> None:
    """Configure Staging Environment secrets."""
    print("\n==================================================")
    print(" 🧪 Step 2: Configure Staging Environment")
    print("==================================================")
    print("Staging uses Account 1 (same Google account as local, but a different key).")

    stage_key = input("Enter your STAGING Gemini API Key (AIzaSy...): ").strip()
    gcp_proj = input("Enter your GCP Staging Project ID (e.g. mas-staging-12345): ").strip()
    sa_path = input("Enter path to Staging Service Account JSON key (or press Enter to skip): ").strip()

    if not gh_ready:
        print("\n⚠️ GitHub CLI ('gh') is not logged in. To configure Staging secrets on GitHub:")
        print(f"1. Open https://github.com/elad823/bots-agents/settings/environments")
        print(f"2. Add environment 'staging' with secrets:")
        print(f"   • GEMINI_API_KEY = {stage_key[:8]}... (hidden)")
        print(f"   • GCP_PROJECT_ID = {gcp_proj}")
        if sa_path:
            print(f"   • GCP_SA_KEY     = Contents of {sa_path}")
        return

    if stage_key:
        set_github_secret("GEMINI_API_KEY", stage_key, "staging")
    if gcp_proj:
        set_github_secret("GCP_PROJECT_ID", gcp_proj, "staging")
    if sa_path and Path(sa_path).expanduser().is_file():
        sa_content = Path(sa_path).expanduser().read_text(encoding="utf-8")
        set_github_secret("GCP_SA_KEY", sa_content, "staging")


def setup_production_env(gh_ready: bool) -> None:
    """Configure Production Environment with mandatory re-auth & isolation check."""
    print("\n==================================================")
    print(" 🛡️ Step 3: Configure Production Environment")
    print("==================================================")
    print("🛑 MANDATORY ACCOUNT ISOLATION & RE-AUTHENTICATION CHECK:")
    print("   You specified that Production MUST use a TOTALLY DIFFERENT Google Account")
    print("   from Test/Staging to guarantee rate-limit isolation and security boundaries.")
    print("--------------------------------------------------")

    reauth_confirm = input("Have you signed into your separate PRODUCTION account to get this key? [y/N]: ").strip().lower()
    if reauth_confirm not in ("y", "yes"):
        print("⚠️ Aborting Production setup until you sign into your Production account.")
        print("   Visit https://aistudio.google.com/app/apikey from your dedicated Prod account.")
        return

    prod_key = input("Enter your PRODUCTION Gemini API Key (from separate Prod account): ").strip()
    prod_gcp_proj = input("Enter your PRODUCTION GCP Project ID: ").strip()
    prod_sa_path = input("Enter path to PRODUCTION Service Account JSON key (or press Enter to skip): ").strip()

    if not gh_ready:
        print("\n⚠️ GitHub CLI ('gh') is not logged in. To configure Production secrets on GitHub:")
        print(f"1. Open https://github.com/elad823/bots-agents/settings/environments")
        print(f"2. Add environment 'production'")
        print(f"3. Enable 'Required reviewers' protection rule.")
        print(f"4. Add secrets:")
        print(f"   • GEMINI_API_KEY = {prod_key[:8]}... (hidden)")
        print(f"   • GCP_PROJECT_ID = {prod_gcp_proj}")
        if prod_sa_path:
            print(f"   • GCP_SA_KEY     = Contents of {prod_sa_path}")
        return

    if prod_key:
        set_github_secret("GEMINI_API_KEY", prod_key, "production")
    if prod_gcp_proj:
        set_github_secret("GCP_PROJECT_ID", prod_gcp_proj, "production")
    if prod_sa_path and Path(prod_sa_path).expanduser().is_file():
        sa_content = Path(prod_sa_path).expanduser().read_text(encoding="utf-8")
        set_github_secret("GCP_SA_KEY", sa_content, "production")

    print("\n✅ Production secrets configured.")
    print("👉 IMPORTANT: Visit https://github.com/elad823/bots-agents/settings/environments/production")
    print("   and ensure 'Required reviewers' is enabled so production deployments require approval.")


def main() -> None:
    print("==================================================")
    print(" 🤖 MAS Multi-Environment Setup & Secret Guard")
    print("==================================================")

    gh_ready = check_gh_installed()
    if not gh_ready:
        print("ℹ️ Note: GitHub CLI ('gh') is not currently authenticated.")
        print("   Run 'gh auth login' in your terminal if you want this script to automatically")
        print("   push secrets directly to your GitHub repository.")
    else:
        print("✅ GitHub CLI is authenticated and ready to configure remote secrets.")

    print("\nWhat would you like to configure?")
    print("  1) Local (.env only)")
    print("  2) Staging (GitHub Environment 'staging')")
    print("  3) Production (GitHub Environment 'production' with Re-Auth Gate)")
    print("  4) All three (Local, Staging, Production)")
    print("  q) Quit")

    choice = input("\nEnter choice [1-4, q]: ").strip().lower()

    if choice == "1":
        setup_local_env()
    elif choice == "2":
        setup_staging_env(gh_ready)
    elif choice == "3":
        setup_production_env(gh_ready)
    elif choice == "4":
        setup_local_env()
        setup_staging_env(gh_ready)
        setup_production_env(gh_ready)
    else:
        print("Exiting.")
        return

    # Post-configuration secret scan
    print("\n--------------------------------------------------")
    print("Running pre-flight secret leak scan...")
    run_cmd([sys.executable, str(WORKSPACE_ROOT / "scripts" / "validate_secrets.py")], capture_output=False)


if __name__ == "__main__":
    main()
