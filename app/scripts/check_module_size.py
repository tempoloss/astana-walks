"""Fail when a module grows past its size budget: walks/*.py and web/*.py > 800 lines, web/static/js/*.js > 800,
tests/*.py > 1000."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGETS = (  # (folder, pattern, limit in lines)
    ("walks", "*.py", 800),
    ("web", "*.py", 800),
    ("web/static/js", "*.js", 800),
    ("tests", "*.py", 1000),
)

too_big = [
    f"{path.relative_to(ROOT).as_posix()}: {n} lines (limit {limit})"
    for folder, pattern, limit in BUDGETS
    for path in sorted((ROOT / folder).glob(pattern))
    if (n := len(path.read_text(encoding="utf-8").splitlines())) > limit
]
if too_big:
    sys.exit("module too large:\n" + "\n".join(too_big))
