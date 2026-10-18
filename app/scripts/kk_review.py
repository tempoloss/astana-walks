"""Write docs/i18n_kk_review.md: every Kazakh UI string added on this branch, for a native speaker to check.

A key counts as added when it is in the string tables of the working tree (app/i18n.py, app/i18n_panels.py,
app/walks/i18n*.py) and not in the same file of the base branch (`main` by default). Each row is
(key, Kazakh, Russian for context); the table is made from the code, not retyped.

    uv run python scripts/kk_review.py [--base main]
"""

from __future__ import annotations

import argparse
import importlib
import re
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
OUT = REPO / "docs" / "i18n_kk_review.md"
KEY = re.compile(r'^    "([A-Za-z0-9_]+)": ', re.M)
# (file in app/, module, table name; None: the module's one upper-case dict)
TABLES = (
    ("i18n.py", "i18n", "UI"),
    ("i18n_panels.py", "i18n_panels", "PANEL"),
    ("walks/i18n.py", "walks.i18n", "STRINGS"),
    ("walks/i18n_sources.py", "walks.i18n_sources", None),
    ("walks/i18n_weather.py", "walks.i18n_weather", "WEATHER_STRINGS"),
    ("walks/i18n_cuisine.py", "walks.i18n_cuisine", "CUISINE"),
    ("walks/profile.py", "walks.profile", "_ITEM"),
)


def _base_keys(base: str, rel: str) -> set[str]:
    res = subprocess.run(
        ["git", "show", f"{base}:app/{rel}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return set(KEY.findall(res.stdout)) if res.returncode == 0 else set()


def _table(module: str, name: str | None) -> dict:
    mod = importlib.import_module(module)
    if name:
        return getattr(mod, name)
    return next(v for k, v in vars(mod).items() if isinstance(v, dict) and v and k.isupper())


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="main")
    args = ap.parse_args()
    rows: list[tuple[str, str, str, str]] = []
    for rel, module, name in TABLES:
        path = APP / rel
        if not path.is_file():
            continue
        old = _base_keys(args.base, rel)
        added = [k for k in KEY.findall(path.read_text(encoding="utf-8")) if k not in old]
        table = _table(module, name)
        rows += [(rel, k, table[k][0], table[k][1]) for k in added if k in table]
    lines = [
        "# Kazakh strings to check",
        "",
        f"Made by `app/scripts/kk_review.py` from the string tables: {len(rows)} entries that this "
        f"branch added (base `{args.base}`). Columns: key, Kazakh, Russian for context. "
        "A native speaker checks the Kazakh.",
        "",
    ]
    for rel in dict.fromkeys(r[0] for r in rows):
        lines += [f"## `app/{rel}`", "", "| key | kk | ru |", "| --- | --- | --- |"]
        lines += [f"| `{k}` | {_cell(kk)} | {_cell(ru)} |" for f, k, kk, ru in rows if f == rel]
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} entries -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
