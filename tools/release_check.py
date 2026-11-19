"""Before publishing: what would go to the repository, and is anything personal in it?

    python tools/release_check.py

Lists the files that are published -- only the files and folders named in PUBLISHED_FILES and
PUBLISHED_DIRS below, without build leftovers and shortcuts; anything else at the top of the
project stays on this computer -- and searches them for things that must not leave it:
the name of the Windows user, absolute paths of this computer, e-mail addresses, anything
that looks like an API key or a proxy address with a password.  Exit code 1 when something is found.
"""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The whole list of what is published from the top of the project.  A new file or folder there is
# not published until it is named here, so the user's data, build folders and private notes can
# lie next to the code and never be picked up by accident.
PUBLISHED_FILES = {".gitignore", "LICENSE", "README.md", "README.ru.md", "app.py", "requirements.txt",
                   "requirements-build.txt", "start.bat"}
PUBLISHED_DIRS = {"docs", "primesets", "tests", "tools", "web"}
SKIP_DIRS = {"data", "screenshots", "release", ".build", "dist", "build", "__pycache__", ".git", ".venv", "venv",
             ".vscode", ".idea"}
SKIP_SUFFIX = {".lnk", ".pyc", ".pyo", ".spec"}
TEXT_SUFFIX = {".py", ".js", ".css", ".html", ".json", ".md", ".txt", ".bat", ".svg", ".toml", ".cfg", ".ini", ".yml", ".yaml", ""}

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL = ("noreply@anthropic.com", "@example.", ".example", "@anthropic-ai/")
KEYLIKE = re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,})\b")
PROXY_WITH_PASSWORD = re.compile(r"https?://[^\s:/@\"'<>{}]+:[^\s:/@\"'<>{}]+@(?!proxy\.example)[A-Za-z0-9.-]+")
COPYRIGHT_LINE = re.compile(r"^\s*Copyright \(c\) \d{4}\b")
ABSOLUTE = re.compile(r"\b[A-Za-z]:\\\\?(?:Users|pj\d|Documents and Settings)\b", re.I)


def files():
    found = [ROOT / name for name in PUBLISHED_FILES if (ROOT / name).is_file()]
    for folder in PUBLISHED_DIRS:
        found += [path for path in (ROOT / folder).rglob("*") if path.is_file()]
    for path in sorted(found):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts) or path.suffix.lower() in SKIP_SUFFIX:
            continue
        yield path, rel


def left_out():
    """What lies at the top of the project and is neither published nor a known leftover."""
    names = []
    for path in sorted(ROOT.iterdir()):
        if path.name in PUBLISHED_FILES or path.name in PUBLISHED_DIRS or path.name in SKIP_DIRS:
            continue
        if path.suffix.lower() in SKIP_SUFFIX:
            continue
        names.append(path.name + ("/" if path.is_dir() else ""))
    return names


def main() -> int:
    user = getpass.getuser()
    marks = {user, str(Path.home()), str(ROOT), str(ROOT.parent)}
    marks = {m for m in marks if m and len(m) > 3}
    found = []
    listed = []
    for path, rel in files():
        listed.append(rel.as_posix())
        if path.suffix.lower() not in TEXT_SUFFIX:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            low = line.lower()
            for mark in marks:
                if mark == user and COPYRIGHT_LINE.match(line):
                    continue            # the author signed the license with this name: published on purpose
                if mark.lower() in low or mark.replace("\\", "/").lower() in low:
                    found.append((rel, n, "this computer's user or folder"))
            for hit in EMAIL.findall(line):
                if not any(ok in hit or ok in line for ok in ALLOWED_EMAIL):
                    found.append((rel, n, "an e-mail address"))
            if KEYLIKE.search(line):
                found.append((rel, n, "something that looks like an API key"))
            if PROXY_WITH_PASSWORD.search(line) and "логин:пароль" not in line and "login:pass" not in low and "me:secret" not in line:
                found.append((rel, n, "an address with a name and a password"))
            if ABSOLUTE.search(line) and rel.as_posix() != "tools/release_check.py":
                found.append((rel, n, "an absolute path of some computer"))
    out = sys.stdout.buffer
    out.write(f"files to publish: {len(listed)}\n".encode())
    for name in listed:
        out.write(f"  {name}\n".encode("utf-8"))
    extra = left_out()
    if extra:
        out.write(("not on the list, stays on this computer: " + ", ".join(extra) + "\n").encode("utf-8"))
    if not found:
        out.write(b"nothing personal found\n")
        return 0
    out.write(f"\nLOOK AT THESE ({len(found)}):\n".encode())
    for rel, n, what in found:
        out.write(f"  {rel.as_posix()}:{n}: {what}\n".encode("utf-8"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
