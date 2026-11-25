"""PostToolUse hook: lint Python files after Edit/Write with ruff.

Rules: pycodestyle errors and warnings (E, W), pyflakes (F), and isort (I).
Line length follows .claude/rules/code style.md (100).
If ruff findings exist, exit code 2 sends them back to Claude so it can fix them.
If ruff is not installed, print a notice and do not block the edit.
"""

import json
import shutil
import subprocess
import sys

LINE_LENGTH = "100"
RULES = "E,W,F,I"


def run_ruff(file_path: str) -> subprocess.CompletedProcess[str]:
    """Run ruff check on one file and return the completed process."""
    return subprocess.run(
        [
            "ruff",
            "check",
            "--output-format",
            "concise",
            "--line-length",
            LINE_LENGTH,
            "--select",
            RULES,
            file_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    """Lint the edited Python file and report findings to Claude."""
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py"):
        return 0
    if shutil.which("ruff") is None:
        print("Lint skipped: ruff is not installed. Run `pip install ruff`.", file=sys.stderr)
        return 0
    result = run_ruff(file_path)
    if result.returncode != 0:
        findings = (result.stdout or result.stderr).strip()
        print(f"Lint failed for {file_path}. Fix these findings:\n{findings}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
