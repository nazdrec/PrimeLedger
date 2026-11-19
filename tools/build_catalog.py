"""Build (or refresh) the prime set catalog from warframe.market and the DE drop tables.

Usage:  python tools/build_catalog.py [--force]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from primesets import catalog, config, i18n, settings  # noqa: E402
from primesets.cache import DiskCache  # noqa: E402
from primesets.wfm import FetchError, WfmClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download the item list and drop tables")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    cache = DiskCache(config.CACHE_DIR)
    wfm = WfmClient(cache)
    started = time.time()
    last = {"stage": None, "shown": 0.0}

    def progress(stage: str, done: int, total: int) -> None:
        now = time.time()
        if stage != last["stage"] or done == total or now - last["shown"] > 5:
            print(f"  {stage}: {done}/{total}", flush=True)
            last["stage"], last["shown"] = stage, now

    try:
        i18n.set_language(settings.language())
        cat = catalog.build(wfm, cache, progress, force=args.force, lang=settings.language(),
                            game_lang=settings.game_language())
    except FetchError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    dt = cat["droptables"]
    print(f"Готово за {time.time() - started:.0f} с: комплектов {len(cat['sets'])}, частей {len(cat['part_index'])}; "
          f"запросов к API {wfm.api.requests_made}, ошибок {wfm.api.errors}")
    print(f"Таблицы дропа DE: {'есть' if dt['available'] else 'НЕТ'}, обновлены «{dt['updated']}», "
          f"реликвий {dt['relic_count']}, падают в миссиях {dt['active_count']}")
    if cat["failed_sets"]:
        print("Не загрузились:", ", ".join(cat["failed_sets"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
