"""Fail when a file of the repo names the owner's private infrastructure (gateway profile / model ids, hosts, networks).

Scans every text file that git tracks or would track (`git ls-files --cached --others --exclude-standard`; the repo
root is two levels above this script) for the pattern below, case-insensitively, and lists each hit as
`path:line: match`. Nothing is excluded but binary files (a NUL byte in the first 8 KiB) and lockfiles, so data/ and
the demo answer cache are read too; git-ignored files (app/.env.demo) are not looked at. A non-empty text file that
is not valid UTF-8 (UTF-16 / UTF-32 with a byte-order mark, Windows-1251, ...) is a failure in itself, listed as
`path: not valid UTF-8`, because it would otherwise pass unread. The hosts are matched as hostnames (dot-delimited),
not as a bare substring, so an ordinary word such as a place name does not trip it.
The pattern is written with character classes (`aig[w]`) so that this file does not contain what it searches for.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(
    r"aig[w]"
    r"|alema[i]"
    r"|[.]dpar[.]dev"
    r"|dpar[.]dev"
    r"|aig[w][.]token"
    r"|109[.]199[.]99[.]117"
    r"|10[.]10[.]210[.]",
    re.IGNORECASE,
)
SKIP_NAMES = {
    "uv.lock",
    "package-lock.json",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
}
BINARY_PROBE = 8192
WIDE_BOMS = (
    b"\xff\xfe",
    b"\xfe\xff",
)  # UTF-16 / UTF-32 text is full of NUL bytes without being binary


def candidate_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [ROOT / name for name in sorted(set(out.split("\0"))) if name]


def scan(path: Path, root: Path = ROOT) -> list[str]:
    """`path:line: match` for every hit in a text file, `path: not valid UTF-8` for a text file that does not decode;
    [] for a lockfile, an empty file, a binary or a missing file. The file is read and decoded once."""
    if path.name in SKIP_NAMES:
        return []
    try:
        data = path.read_bytes()
    except OSError:
        return []  # deleted in the working tree
    if not data or (b"\0" in data[:BINARY_PROBE] and not data.startswith(WIDE_BOMS)):
        return []
    rel = path.relative_to(root).as_posix()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{rel}: not valid UTF-8"]
    return [
        f"{rel}:{n}: {m.group(0).lower()}"
        for n, line in enumerate(text.splitlines(), 1)
        for m in PATTERN.finditer(line)
    ]


def main() -> int:
    hits = [hit for path in candidate_files() for hit in scan(path)]
    if hits:
        sys.exit("private identifiers or non-UTF-8 text files in the repo:\n" + "\n".join(hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
