"""SessionStart hook: load CHANGELOG.md into the session context.

Stdout from a SessionStart hook is added to Claude's context, so Claude
starts each session knowing the current decisions and open items.
ARCHIVE.md is intentionally not loaded here.
"""

import os
import sys

CHANGELOG = "CHANGELOG.md"


def main() -> int:
    """Print the changelog to stdout when it exists."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    path = os.path.join(project_dir, CHANGELOG)
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as handle:
        print("Project changelog (read at session start):\n")
        print(handle.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
