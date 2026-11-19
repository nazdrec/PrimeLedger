"""Подготовка скриншотов к чтению и уборка после импорта (для работы через чат Claude).

    python tools/screenshots.py list              что лежит в папке screenshots
    python tools/screenshots.py prepare           нарезать большие скриншоты на плитки
    python tools/screenshots.py archive           убрать обработанные в screenshots/_done/<дата>

Зачем плитки: модель видит картинку шириной не больше ~1568 пикселей, более крупные
уменьшаются, и мелкие подписи в инвентаре читаются хуже.  Плитки сохраняют исходный
масштаб и перекрываются, чтобы предмет, разрезанный краем одной плитки, целиком попал
в соседнюю.  Оригиналы не меняются.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from primesets import config, shots  # noqa: E402


def cmd_list(_args) -> int:
    files = shots.originals()
    print(f"Папка: {config.SCREENSHOT_DIR}")
    if not files:
        print("Скриншотов нет.")
        return 0
    for f in files:
        size = shots.image_size(f)
        dims = f"{size[0]}x{size[1]}" if size else ""
        print(f"  {f.name}  {dims}  {f.stat().st_size // 1024} КБ")
    return 0


def cmd_prepare(args) -> int:
    if not shots.have_pillow():
        print("Pillow не установлен: читайте оригиналы как есть (pip install pillow — для нарезки).")
        return 1
    files = shots.originals()
    if not files:
        print("Скриншотов нет.")
        return 0
    if shots.TILE_DIR.exists():
        shutil.rmtree(shots.TILE_DIR)
    for f in files:
        size = shots.image_size(f)
        if size and size[0] <= args.max_side and size[1] <= args.max_side:
            print(f"{f.name}: {size[0]}x{size[1]} — читать целиком: {f}")
            continue
        tiles = shots.make_tiles(f, shots.TILE_DIR, args.max_side)
        dims = f"{size[0]}x{size[1]}" if size else "?"
        print(f"{f.name}: {dims} -> {len(tiles)} плиток")
        for t in tiles:
            print(f"    {t}")
    return 0


def cmd_archive(_args) -> int:
    count = len(shots.originals())
    target = shots.archive()
    if target is None:
        print("Скриншотов нет.")
    else:
        print(f"Перенесено {count} файлов в {target}")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("prepare")
    p.add_argument("--max-side", type=int, default=shots.MAX_SIDE)
    p.set_defaults(fn=cmd_prepare)
    sub.add_parser("archive").set_defaults(fn=cmd_archive)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
