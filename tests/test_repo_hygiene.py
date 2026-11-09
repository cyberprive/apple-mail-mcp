"""The repo is public: it must not carry anyone's real address or home path.

Invariant: no tracked text file contains an email address outside the
reserved example domains, or an absolute /Users/<name> path. Personal details
belong in the caller's own config, never in this repo.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist"}
TEXT_SUFFIXES = {".py", ".js", ".md", ".toml", ".txt", ".example", ".cfg", ".ini", ".yml", ".yaml", ""}
ALLOWED_DOMAINS = ("example.com", "example.org", "example.net")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
HOME_PATH = re.compile(r"/Users/[A-Za-z0-9._-]+")


def _files():
    for p in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.is_file() and (p.suffix in TEXT_SUFFIXES or p.name.startswith(".env")):
            yield p


def test_no_real_email_addresses():
    leaks = []
    for p in _files():
        for m in EMAIL.finditer(p.read_text(errors="ignore")):
            if not m.group(0).lower().endswith(ALLOWED_DOMAINS):
                leaks.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert not leaks, "real-looking addresses in repo:\n" + "\n".join(leaks)


def test_no_absolute_home_paths():
    leaks = []
    for p in _files():
        if p.name == Path(__file__).name:
            continue
        for m in HOME_PATH.finditer(p.read_text(errors="ignore")):
            leaks.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert not leaks, "absolute home paths in repo (use ~):\n" + "\n".join(leaks)
