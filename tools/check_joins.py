"""Проверить, стыкуются ли скриншоты инвентаря: не пропущен ли ряд плиток при прокрутке.

    python tools/check_joins.py                      # папка входящих скриншотов приложения
    python tools/check_joins.py <папка> [-v]         # любая папка, например screenshots\_done\<время>

Сравниваются только картинки; файлы не меняются.  -v печатает каждую пару соседних снимков.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from primesets import config, continuity, shots  # noqa: E402

WHY = {"gap": "НЕ СТЫКУЕТСЯ", "size": "не сверено: снимки разного размера", "nogrid": "не сверено: сетка плиток не найдена"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка стыков между скриншотами инвентаря")
    ap.add_argument("folder", nargs="?", default=str(config.SCREENSHOT_DIR))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    folder = Path(args.folder)
    files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in shots.EXT) if folder.is_dir() else []
    if not continuity.available():
        print("Проверка недоступна: не установлена библиотека Pillow.")
        return 1
    rep = continuity.check(files)
    print(f"Папка: {folder}")
    print(f"Скриншотов: {len(files)}, из них с сеткой плиток инвентаря: {rep['pages']}; "
          f"соседних пар: {rep['pairs']}, стыкуются: {rep['joined']} ({rep['seconds']} с)")
    if args.verbose:
        grid = [f for f in files if continuity.is_grid(f)]
        for a, b in zip(grid, grid[1:]):
            link = continuity.join(a, b)
            verdict = f"стык, сдвиг {link.shift} px" if link.joined else WHY.get(link.why, link.why)
            print(f"  {a.name} -> {b.name}: {verdict}; колонок {link.cells}, отличаются {link.differ}")
    for gap in rep["gaps"]:
        print(f"ПРОПУСК: между «{gap['after']}» и «{gap['before']}» список не стыкуется — похоже, пропущен ряд.")
    for item in rep["unknown"]:
        print(f"Не сверено: «{item['after']}» и «{item['before']}» ({WHY.get(item['why'], item['why'])}).")
    if rep["state"] == "ok":
        print("Пропусков нет: каждый снимок продолжает предыдущий.")
    elif rep["state"] == "unsure":
        print("Ни одна пара не состыковалась: либо ряд пропущен на каждом шаге, либо экран выглядит непривычно.")
    elif rep["state"] == "none" and rep["pages"] < 1:
        print("Сравнивать нечего: снимков сетки инвентаря нет.")
    ends = {"ok": "да", "missing": "НЕТ", "unknown": "не определено"}
    if rep["first"]:
        print(f"Начало списка снято: {ends[rep['start']]} (самый верхний снимок — «{rep['first']}»).")
        print(f"Конец списка снят: {ends[rep['end']]} (самый нижний снимок — «{rep['last']}»).")
    elif rep["pages"] and not rep["gaps"]:
        print("Начало и конец списка не проверены: снимки разного размера или не сверены между собой.")
    return 2 if rep["gaps"] or "missing" in (rep["start"], rep["end"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
