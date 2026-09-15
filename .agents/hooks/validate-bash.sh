#!/usr/bin/env bash
# Antigravity Lifecycle Hook: Validate Bash Commands before run_command executes

set -e

# Read JSON payload from stdin
PAYLOAD=$(cat)

# Inspect command line via Python helper
DECISION=$(python3 - <<EOF
import sys, json

try:
    data = json.loads('''$PAYLOAD''')
    cmd = data.get("toolCall", {}).get("args", {}).get("CommandLine", "")
    
    # Dangerous patterns
    dangerous = ["rm -rf /", "mkfs", "> /dev/sda", ":(){ :|:& };:"]
    for pattern in dangerous:
        if pattern in cmd:
            print(json.dumps({
                "decision": "deny",
                "reason": f"Blocked command containing forbidden dangerous pattern: {pattern}"
            }))
            sys.exit(0)
            
    print(json.dumps({"decision": "allow"}))
except Exception as e:
    # Fail safe: allow by default if parsing error
    print(json.dumps({"decision": "allow"}))
EOF
)

echo "$DECISION"
