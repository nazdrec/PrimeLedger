"""Build dist/<name of the app>.exe -- one file that needs no Python on the user's computer.

    python tools/build_exe.py            build (creates the build environment .build/venv on the first run)
    python tools/build_exe.py --check    only look inside an already built exe

What goes into the exe: the program (app.py, primesets/), the page (web/) and the libraries it
uses (Pillow, anthropic), with the license texts of all of them.  What never goes in: data/,
screenshots/, settings, keys, logs -- every user starts with an empty app and connects their own
account.  After the build the exe is opened and its list of files is checked for exactly that.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from primesets import APP_NAME  # noqa: E402

BUILD = ROOT / ".build"
VENV = BUILD / "venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
EXE = ROOT / "dist" / f"{APP_NAME}.exe"
LICENSES = BUILD / "licenses"
PRIVATE = ("data/", "screenshots/", "settings.json", "secrets.json", "inventory.json", "mastery.json", "history.json",
           ".log", ".lnk", "tests/", ".build/")


def run(cmd, **kw) -> None:
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def environment() -> None:
    if not PY.is_file():
        print("creating the build environment", VENV, flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV)
    run([PY, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([PY, "-m", "pip", "install", "--quiet", "-r", ROOT / "requirements.txt", "-r", ROOT / "requirements-build.txt"])


def licenses() -> None:
    """The license of the program and of everything packed with it: they travel inside the exe."""
    shutil.rmtree(LICENSES, ignore_errors=True)
    LICENSES.mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", LICENSES / "LICENSE.txt")
    run([PY, ROOT / "tools" / "third_party.py", LICENSES / "THIRD_PARTY_NOTICES.txt"])


def build() -> None:
    licenses()
    run([PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
         "--name", APP_NAME,
         "--icon", ROOT / "web" / "app.ico",
         "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
         "--add-data", f"{LICENSES}{os.pathsep}licenses",
         "--distpath", ROOT / "dist", "--workpath", BUILD / "work", "--specpath", BUILD,
         "--exclude-module", "tkinter",
         ROOT / "app.py"], cwd=ROOT)


INSIDE = r"""
import json, marshal, os, sys, tempfile
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

exe, marks = sys.argv[1], [m.encode("utf-8") for m in sys.argv[2:]]
variants = []
for m in marks:
    variants += [m, m.replace(b"\\", b"/"), m.replace(b"\\", b"\\\\"), m.decode("utf-8").encode("utf-16-le")]
arch = CArchiveReader(exe)
names, leaks = sorted(arch.toc), []


def scan(where, data):
    if where.replace("\\", "/").lower().endswith("licenses/license.txt"):
        # the author signed the license of the program with a name: it is there on purpose
        data = b"\n".join(ln for ln in data.split(b"\n") if not ln.lstrip().startswith(b"Copyright (c)"))
    low = data.lower()
    if any(v.lower() in low for v in variants):
        leaks.append(where)


for name in names:
    try:
        data = arch.extract(name)
    except Exception:
        continue
    if not isinstance(data, (bytes, bytearray)):
        continue
    scan(name, bytes(data))
    if name.lower().endswith(".pyz"):
        with tempfile.NamedTemporaryFile(suffix=".pyz", delete=False) as tmp:
            tmp.write(data)
        try:
            pyz = ZlibArchiveReader(tmp.name)
            for module in sorted(pyz.toc):
                try:
                    code = pyz.extract(module)
                except Exception:
                    continue
                if code is not None:
                    scan("module " + module, marshal.dumps(code))
        finally:
            os.unlink(tmp.name)
print(json.dumps({"names": names, "leaks": leaks}))
"""


def check() -> int:
    """Open the exe (every packed file and every Python module in it) and make sure nothing of the
    developer's own is inside: no data files, no name of the Windows user, no folder of this computer."""
    if not EXE.is_file():
        print("no exe:", EXE)
        return 1
    marks = sorted({getpass.getuser(), str(Path.home()), str(ROOT), str(ROOT.parent)} - {""})
    marks = [m for m in marks if len(m) > 3]
    out = subprocess.run([str(PY), "-c", INSIDE, str(EXE)] + marks, capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if out.returncode != 0:
        print(out.stderr[-2000:])
        return 1
    report = json.loads(out.stdout.strip().splitlines()[-1])
    names = [n.replace("\\", "/") for n in report["names"]]
    # the project's own Markdown (READMEs, notes) has no business inside; libraries keep theirs under *.dist-info
    bad = [n for n in names if any(mark in n.lower() for mark in PRIVATE)
           or (n.lower().endswith(".md") and ".dist-info/" not in n.lower())]
    web = [n for n in names if n.startswith("web/")]
    need = ["web/index.html", "web/app.js", "web/styles.css", "web/i18n/en.json", "web/i18n/de.json", "web/i18n/fr.json",
            "web/i18n/pl.json", "web/i18n/zh.json", "licenses/LICENSE.txt", "licenses/THIRD_PARTY_NOTICES.txt"]
    missing = [n for n in need if n not in names]
    print(f"{EXE.name}: {EXE.stat().st_size / 1e6:.1f} MB, {len(names)} packed files, page files: {len(web)}")
    print("private files inside:", bad or "none")
    print("page files missing:", missing or "none")
    print("developer's name or folders inside:", report["leaks"][:20] or "none")
    return 1 if (bad or missing or report["leaks"]) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="only look inside the exe that is already built")
    args = ap.parse_args()
    if not args.check:
        environment()
        build()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
