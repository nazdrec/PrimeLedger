"""The licenses of everything the exe carries besides the program itself.

    <build python> tools/third_party.py OUT_FILE

Run by tools/build_exe.py inside the build environment, where only the libraries of the app
and the build tools are installed.  The exe is a copy of Python, of those libraries and of the
program: their licenses ask that the license texts travel with every copy, so the list is
packed into the exe (shown in the app: Settings -> Licenses).
"""
from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

# tools that build the exe but are not copied into it
BUILD_ONLY = {"pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
              "pywin32-ctypes", "packaging", "macholib"}
LICENSE_FILE = re.compile(r"(?i)(^|/)(licen[cs]e|copying|notice)[^/]*$")
LINE = "=" * 78


def license_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    for field in ("License-Expression", "License"):
        value = (meta.get(field) or "").strip()
        if value and len(value) < 120 and "\n" not in value:
            return value
    found = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    return ", ".join(found) or "see the text below"


def texts_of(dist: metadata.Distribution) -> list:
    out = []
    for item in dist.files or []:
        name = str(item).replace("\\", "/")
        if ".dist-info/" in name and LICENSE_FILE.search(name):
            try:
                out.append((name.split(".dist-info/", 1)[1], dist.locate_file(item).read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return out


def main() -> int:
    target = Path(sys.argv[1])
    parts = [
        "THIRD-PARTY SOFTWARE IN THIS PROGRAM",
        "",
        "The exe is built with PyInstaller and contains, besides the program itself (MIT license,",
        "see above): the Python runtime and the libraries listed here.  Each of them stays under its",
        "own license; the texts follow.  The PyInstaller bootloader is distributed under the GPL with",
        "an exception that allows bundling programs under any license (https://pyinstaller.org/en/stable/license.html).",
        "",
    ]
    dists = sorted((d for d in metadata.distributions() if (d.metadata.get("Name") or "").lower() not in BUILD_ONLY),
                   key=lambda d: (d.metadata.get("Name") or "").lower())
    seen = set()
    listing = []
    for dist in dists:
        name = dist.metadata.get("Name") or "?"
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        listing.append(f"  {name} {dist.version} -- {license_of(dist)}")
    parts += [f"  Python {sys.version.split()[0]} -- PSF-2.0"] + listing + [""]

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        parts += [LINE, f"Python {sys.version.split()[0]}", LINE, python_license.read_text(encoding="utf-8", errors="replace"), ""]
    seen.clear()
    for dist in dists:
        name = dist.metadata.get("Name") or "?"
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        home = dist.metadata.get("Home-page") or next((u.split(",", 1)[1].strip() for u in dist.metadata.get_all("Project-URL") or []
                                                      if "," in u), "")
        parts += [LINE, f"{name} {dist.version} -- {license_of(dist)}" + (f"\n{home}" if home else ""), LINE]
        texts = texts_of(dist)
        if not texts:
            parts += ["(the package carries no license file; see its page for the text of the license named above)", ""]
        for file_name, text in texts:
            parts += [f"--- {file_name} ---", text.strip(), ""]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    print(f"third-party notices: {len(listing)} libraries, {target.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
