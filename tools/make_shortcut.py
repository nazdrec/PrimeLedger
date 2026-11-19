"""Создать ярлык приложения (и значок для него) -- для запуска из исходников.

    python tools/make_shortcut.py             ярлык в папке приложения
    python tools/make_shortcut.py --desktop   ещё и на рабочем столе

Ярлык запускает app.py через pythonw.exe — без окна консоли.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from primesets import APP_NAME  # noqa: E402

ICON = ROOT / "web" / "app.ico"
NAME = f"{APP_NAME}.lnk"


def make_icon() -> bool:
    """Draw the app icon (the same mark as in the header). Needs Pillow; without it the shortcut gets Python's icon."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    size = 512
    c0, c1 = (42, 120, 214), (98, 80, 214)
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=144, fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    draw = ImageDraw.Draw(img)
    mid = size / 2
    outer = [(mid, 88), (size - 88, mid), (mid, size - 88), (88, mid)]
    draw.line(outer + [outer[0], outer[1]], fill=(255, 255, 255, 255), width=32, joint="curve")
    draw.polygon([(mid, 176), (size - 176, mid), (mid, size - 176), (176, mid)], fill=(255, 255, 255, 255))
    img.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return True


def pythonw() -> str:
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.is_file() else exe)


def create(link: Path) -> None:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PS_LNK);"
        "$s.TargetPath=$env:PS_TARGET;$s.Arguments=$env:PS_ARGS;$s.WorkingDirectory=$env:PS_CWD;"
        "$s.Description=$env:PS_DESC;if($env:PS_ICON){$s.IconLocation=$env:PS_ICON};$s.Save()"
    )
    env = dict(os.environ)
    env.update({
        "PS_LNK": str(link),
        "PS_TARGET": pythonw(),
        "PS_ARGS": f'"{ROOT / "app.py"}"',
        "PS_CWD": str(ROOT),
        "PS_DESC": f"{APP_NAME}: прайм-комплекты Warframe",
        "PS_ICON": str(ICON) if ICON.is_file() else "",
    })
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env, check=True)
    print(f"Ярлык: {link}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desktop", action="store_true", help="создать ярлык и на рабочем столе")
    args = ap.parse_args()
    if not make_icon():
        print("Pillow не найден: ярлык будет со значком Python.")
    create(ROOT / NAME)
    if args.desktop:
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              "[Console]::OutputEncoding=[Text.Encoding]::UTF8;[Environment]::GetFolderPath('Desktop')"],
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode == 0 and out.stdout.strip():
            desktop = Path(out.stdout.strip())
        create(desktop / NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
