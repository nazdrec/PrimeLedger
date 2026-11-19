"""Put together what gets published: the files of the repository and the exe for the release.

    python tools/make_release.py

Makes the folder release/ (it is never published itself):
    release/github/                 exactly the files of the repository -- nothing of the user's own
    release/<name of the app>.exe   the program to attach to the GitHub release
    release/THIRD_PARTY_NOTICES.txt the licenses of the libraries inside the exe
    release/SHA256.txt              the checksum of the exe, for the text of the release

Before anything is copied the files are searched for personal data (tools/release_check.py) and
the exe is opened and searched too (tools/build_exe.py --check): the folder is made only when
both find nothing.  A git repository started inside release/github (its .git folder) is kept.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import release_check  # noqa: E402
from primesets import APP_NAME, __version__  # noqa: E402

RELEASE = ROOT / "release"
REPO = RELEASE / "github"
EXE = ROOT / "dist" / f"{APP_NAME}.exe"
NOTICES = ROOT / ".build" / "licenses" / "THIRD_PARTY_NOTICES.txt"


def newest_source() -> float:
    return max(path.stat().st_mtime for path, rel in release_check.files()
               if rel.parts[0] in ("primesets", "web") or rel.name in ("app.py", "LICENSE", "requirements.txt"))


def main() -> int:
    out = sys.stdout
    if release_check.main() != 0:
        print("\nNothing was copied: look at the lines above first.")
        return 1
    if not EXE.is_file():
        print(f"\nThere is no {EXE.name} yet: run  python tools/build_exe.py  first.")
        return 1
    if EXE.stat().st_mtime < newest_source():
        print(f"\n{EXE.name} is older than the source: run  python tools/build_exe.py  and then this again.")
        return 1
    check = subprocess.run([sys.executable, str(ROOT / "tools" / "build_exe.py"), "--check"])
    if check.returncode != 0:
        print("\nNothing was copied: the exe did not pass the check.")
        return 1

    # the repository: wiped and copied anew, except a git history the user may have started there
    REPO.mkdir(parents=True, exist_ok=True)
    for item in REPO.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    count = 0
    for path, rel in release_check.files():
        target = REPO / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        count += 1

    for stale in RELEASE.glob("*.exe"):          # a build under an earlier name or version
        if stale.name != EXE.name:
            stale.unlink()
    shutil.copyfile(EXE, RELEASE / EXE.name)
    if NOTICES.is_file():
        shutil.copyfile(NOTICES, RELEASE / NOTICES.name)
    digest = hashlib.sha256(EXE.read_bytes()).hexdigest()
    (RELEASE / "SHA256.txt").write_text(f"{digest}  {EXE.name}\n", encoding="utf-8")

    out.write(f"\n{APP_NAME} {__version__}: ready to publish\n")
    out.write(f"  repository files: {count}  ->  release/github\n")
    out.write(f"  program:          release/{EXE.name}  ({EXE.stat().st_size / 1e6:.1f} MB)\n")
    out.write(f"  SHA-256:          {digest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
