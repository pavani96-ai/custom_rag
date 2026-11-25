"""PreToolUse hook: block Edit/Write to secret and key files.

Enforces .claude/rules/security.md: never commit .env or key files.
Reads the hook payload from stdin and emits a deny decision as JSON.
"""

import fnmatch
import json
import os
import sys

BLOCKED_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_rsa*",
    "credentials*",
    "*credentials*.json",
    "service-account*.json",
]
ALLOWED_NAMES = {".env.example"}


def is_secret_file(file_path: str) -> bool:
    """Return True when the file name matches a blocked secret pattern."""
    name = os.path.basename(file_path)
    if name in ALLOWED_NAMES:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_PATTERNS)


def deny(reason: str) -> None:
    """Print a PreToolUse deny decision and exit successfully."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload))


def main() -> int:
    """Read the hook payload and deny writes to secret files."""
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    if file_path and is_secret_file(file_path):
        deny(
            f"Blocked: '{os.path.basename(file_path)}' looks like a secret file. "
            "Keep secrets in environment variables; only .env.example may be committed."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
