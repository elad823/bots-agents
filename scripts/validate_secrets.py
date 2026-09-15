#!/usr/bin/env python3
"""Pre-commit and CI Secret Scanner for Autonomous Multi-Agent System (MAS).

Ensures that no live API keys, service account credentials, private keys,
or high-entropy authentication tokens are committed to source control.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Sensitive regex patterns to block
SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z-_]{35}", "Google AI Studio / Gemini API Key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Cryptographic Key"),
    (r"(?:api[_-]?key|apikey|secret[_-]?key)\s*[:=]\s*['\"][0-9a-zA-Z\-_]{20,}['\"]", "Generic High-Entropy API Key"),
    (r"ghp_[0-9a-zA-Z]{36}", "GitHub Personal Access Token"),
    (r"xox[baprs]-[0-9a-zA-Z]{10,48}", "Slack Token"),
    (r"\"private_key\"\s*:\s*\"-----BEGIN", "Google Service Account Private Key JSON"),
]

# Patterns allowed as legitimate placeholder documentation
ALLOWED_PLACEHOLDERS = [
    "mock_dev_key",
    "AIzaSy_placeholder_key_here",
    "AIzaSy_staging_secret_key_placeholder",
    "AIzaSy_production_secret_key_placeholder",
    "your_gemini_api_key_here",
    "mock_key",
]

# Directories and files ignored during scanning
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "node_modules",
    "data",
}

IGNORE_FILES = {
    ".env",
    ".env.local",
    "mas_database.db",
}


def scan_file(filepath: Path) -> list[str]:
    """Scan a single file for known secret patterns."""
    violations: list[str] = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        print(f"Warning: Could not read {filepath}: {exc}", file=sys.stderr)
        return violations

    for line_num, line in enumerate(content.splitlines(), start=1):
        # Skip comment documentation lines in markdown or test mocks
        if any(allowed in line for allowed in ALLOWED_PLACEHOLDERS):
            continue

        for pattern, desc in SECRET_PATTERNS:
            if re.search(pattern, line):
                violations.append(f"  Line {line_num}: [{desc}] match found: '{line.strip()[:60]}...'")

    return violations


def main() -> int:
    """Scan workspace files and return status code."""
    workspace_root = Path(__file__).resolve().parent.parent
    total_violations = 0

    print("==================================================")
    print(" 🔒 MAS Pre-Flight Security & Secret Audit Scanner")
    print(f" Target Directory: {workspace_root}")
    print("==================================================")

    for root, dirs, files in os.walk(workspace_root):
        # Prune ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            if file in IGNORE_FILES:
                continue
            if file.endswith((".db", ".db-wal", ".db-shm", ".pyc", ".png", ".jpg", ".ico")):
                continue

            file_path = Path(root) / file
            rel_path = file_path.relative_to(workspace_root)
            violations = scan_file(file_path)

            if violations:
                print(f"\n❌ [SECRET LEAK DETECTED] in {rel_path}:")
                for v in violations:
                    print(v)
                total_violations += len(violations)

    print("\n--------------------------------------------------")
    if total_violations > 0:
        print(f"❌ AUDIT FAILED: {total_violations} secret leak(s) detected.")
        print("Remove or mask all credentials before committing or pushing.")
        print("--------------------------------------------------")
        return 1

    print("✅ AUDIT PASSED: Zero secret leaks or exposed keys found.")
    print("--------------------------------------------------")
    return 0


if __name__ == "__main__":
    sys.exit(main())
