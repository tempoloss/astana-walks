"""scripts/check_leaks.py: the private-infrastructure patterns, what it skips, and that the repo is clean.

The private strings are assembled at run time so that this file does not contain them (the checker reads tests too).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_leaks.py"
spec = importlib.util.spec_from_file_location("check_leaks", SCRIPT)
check_leaks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_leaks)

GATEWAY = "ai" + "gw"
PROFILE = "ale" + "mai"
HOST = "dp" + "ar." + "dev"
IP = ".".join(["109", "199", "99", "117"])
NET = ".".join(["10", "10", "210", "5"])


@pytest.mark.parametrize(
    "text",
    [
        f"url = https://{GATEWAY}.{HOST}/v1",
        f"LLM_PROFILE_{PROFILE.upper()}_API_KEY_FILE=x",
        f"~/.{GATEWAY}.token",
        f"ssh root@{IP}",
        f"http://{NET}:8000",
        f"host: node1.{HOST}",
    ],
)
def test_private_identifiers_are_found(tmp_path, text):
    f = tmp_path / "notes.txt"
    f.write_text(f"harmless\n{text}\n", encoding="utf-8")
    hits = check_leaks.scan(f, tmp_path)
    assert hits
    assert all(h.startswith("notes.txt:2: ") for h in hits)


def test_ordinary_words_are_not_hits(tmp_path):
    f = tmp_path / "poi.json"
    f.write_text(
        '{"name": "Redpark", "note": "Ledpardon"}\n10.10.2026 and 10.100.5.5 are not an address\n',
        encoding="utf-8",
    )
    assert check_leaks.scan(f, tmp_path) == []


def test_data_files_are_scanned_only_binary_and_lockfiles_are_skipped(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    big = data / "overture_places.json"
    big.write_text('{"a": "' + GATEWAY + '"}', encoding="utf-8")
    assert check_leaks.scan(big, tmp_path) == [f"data/overture_places.json:1: {GATEWAY}"]
    binary = tmp_path / "x.bin"
    binary.write_bytes(b"\x00\x01" + GATEWAY.encode())
    assert check_leaks.scan(binary, tmp_path) == []
    lock = tmp_path / "uv.lock"
    lock.write_text(GATEWAY, encoding="utf-8")
    assert check_leaks.scan(lock, tmp_path) == []


def test_utf16_text_is_a_failure_not_a_skip(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text(
        f"harmless\n{GATEWAY}\n", encoding="utf-16"
    )  # BOM + NUL bytes: neither UTF-8 nor binary
    assert check_leaks.scan(f, tmp_path) == ["notes.md: not valid UTF-8"]


def test_windows_1251_text_is_a_failure(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_bytes("Привет, Астана".encode("cp1251"))
    assert check_leaks.scan(f, tmp_path) == ["notes.txt: not valid UTF-8"]


def test_empty_file_and_utf8_with_bom_are_fine(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    assert check_leaks.scan(empty, tmp_path) == []
    bom = tmp_path / "bom.md"
    bom.write_bytes(b"\xef\xbb\xbf" + GATEWAY.encode())
    assert check_leaks.scan(bom, tmp_path) == [f"bom.md:1: {GATEWAY}"]


def test_the_checker_does_not_contain_what_it_searches_for():
    assert check_leaks.scan(SCRIPT, SCRIPT.parents[2]) == []
