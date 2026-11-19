"""Занести в приложение то, что прочитано со скриншотов (инвентарь, кузница, профиль).

    python tools/import_inventory.py recognized.json [--mode replace|merge] [--dry-run] [--force]

Формат recognized.json (UTF-8):

    {
      "mode": "replace",                      // необязательно; ключ --mode важнее
      "note": "12 скриншотов инвентаря и 3 кузницы от 18.11.2026",
      "parts": [                              // прайм-части и чертежи
        {"name": "Акцельтра Прайм: Ствол", "count": 2, "blueprint": false, "shot": "inv_03.png"},
        {"name": "Мираж Прайм: Система",   "count": 1, "blueprint": true,  "shot": "inv_05.png"},
        {"name": "Акцельтра Прайм",        "count": 1, "blueprint": true,  "count_known": false,
         "shot": "foundry_01.png"},           // чертёж виден в кузнице, но числа рядом нет
        {"name": "Чертёж: Ивара Прайм",    "count": 1, "blueprint": true,  "count_known": false,
         "count_hidden": true, "shot": "inv_19.png"}   // верх плитки срезан краем списка, числа не видно
      ],
      "mastery": [                            // отметки освоения целых предметов
        {"name": "Акцельтра Прайм", "mastered": false, "owned": false, "shot": "foundry_01.png"},
        {"name": "Мираж Прайм",     "mastered": true}
      ]
    }

    blueprint  true  -- на плитке предмет помечен как чертёж;
               false -- это готовая (построенная) часть или предмет: в комплект для продажи не идёт;
               без поля -- неизвестно (будет помечено «проверьте»).
    mode       replace -- parts это полный снимок всех прайм-частей (вкладка инвентаря целиком);
               merge   -- обновить только перечисленные части, остальные оставить.

Имена пишутся так, как они видны на экране (русский или английский клиент).
Скрипт сам сопоставляет их с каталогом warframe.market и печатает отчёт.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from primesets import analysis, catalog, config, i18n, inventory, mastery, settings  # noqa: E402
from primesets.i18n import tr  # noqa: E402
from primesets.cache import DiskCache  # noqa: E402
from primesets.wfm import FetchError, WfmClient  # noqa: E402


def get_catalog() -> dict:
    cache = DiskCache(config.CACHE_DIR)
    lang, game = settings.language(), settings.game_language()
    i18n.set_language(lang)
    cat = catalog.load_cached(cache, None, lang, game)
    if cat is None:
        print("Каталога ещё нет — загружаю с warframe.market (1–2 минуты)...", flush=True)
        cat = catalog.build(WfmClient(cache), cache, None, lang=lang, game_lang=game)
    return cat


def main() -> int:
    ap = argparse.ArgumentParser(description="Импорт распознанных частей и отметок освоения")
    ap.add_argument("file", help="JSON с распознанными данными; «-» читает stdin")
    ap.add_argument("--mode", choices=["replace", "merge"], help="replace: полный снимок; merge: дополнить")
    ap.add_argument("--dry-run", action="store_true", help="только показать отчёт, ничего не записывать")
    ap.add_argument("--force", action="store_true", help="разрешить replace, который сильно уменьшает инвентарь")
    ap.add_argument("--source", default="screenshots")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, list):
        data = {"parts": data}
    parts = data.get("parts") or []
    marks = data.get("mastery") or []
    mode = args.mode or data.get("mode") or "replace"
    note = str(data.get("note") or "")

    try:
        cat = get_catalog()
    except FetchError as exc:
        print(f"ОШИБКА: каталог недоступен: {exc}", file=sys.stderr)
        return 1

    part_ru = {p["slug"]: p["name"] for st in cat["sets"].values() for p in st["parts"]}
    mrep = mastery.import_marks(marks, cat, source=args.source, dry_run=args.dry_run) if marks else None
    mastery_review = mrep["review"] if mrep else []

    rep = None
    if parts:
        rep = inventory.import_entries(parts, cat, mode=mode, source=args.source, note=note, dry_run=args.dry_run,
                                       extra_review=mastery_review, force=args.force)
    elif mastery_review and not args.dry_run:
        inventory.add_review(mastery_review)

    tag = " (ПРОБНЫЙ ПРОГОН, ничего не записано)" if args.dry_run else ""
    if rep:
        print(f"=== Части{tag}: режим {rep['mode']}")
        print(f"Записей прочитано: {rep['entries']}; сопоставлено {len(rep['matched'])} "
              f"-> {rep['distinct_parts']} разных частей, {rep['total_parts']} шт.")
        if rep["refused"]:
            print(f"\n!!! НЕ ЗАПИСАНО: {rep['refused']}")
        ch = rep["changes"]
        print(f"Изменения к прежнему инвентарю: добавлено {len(ch['added'])}, "
              f"убрано {len(ch['removed'])}, изменилось количество {len(ch['changed'])}")
        if ch["removed"]:
            print("  убрано:", ", ".join(part_ru.get(s, s) for s in ch["removed"][:40])
                  + (" ..." if len(ch["removed"]) > 40 else ""))
        unmatched = [r for r in rep["review"] if r["kind"] == "unmatched"]
        if unmatched:
            print(f"\nНЕ СОПОСТАВЛЕНО ({len(unmatched)}) — этих частей нет в инвентаре приложения:")
            for r in unmatched:
                sugg = "; похоже на: " + " | ".join(s["item"] for s in r["suggestions"]) if r["suggestions"] else ""
                print(f"  - «{r['name']}» x{r['count']} [{r.get('shot', '')}]{sugg}")
        checks = [r for r in rep["review"] if r["kind"] in ("check", "conflict")]
        if checks:
            print(f"\nПРОВЕРИТЬ ({len(checks)}):")
            for r in checks:
                print(f"  - «{r['name']}» -> {r.get('ru', '')} x{r['count']}: {r['note']} [{r.get('shot', '')}]")
        skipped = [r for r in rep["skipped"] if r["status"] in ("built", "not_prime")]
        if skipped:
            built = [r for r in skipped if r["status"] == "built"]
            other = [r for r in skipped if r["status"] == "not_prime"]
            if built:
                print(f"\nПропущено как построенные предметы ({len(built)}): "
                      + ", ".join(r["name"] for r in built[:30]))
            if other:
                print(f"Пропущено как не прайм-части ({len(other)}): " + ", ".join(r["name"] for r in other[:30]))

    if mrep is not None:
        print(f"\n=== Освоение{tag}")
        print(f"Отметок применено: {len(mrep['applied'])}, из них изменили состояние: {len(mrep['changed'])}")
        for a in mrep["changed"]:
            print(f"  - {a['item']}: {tr(mastery.STATE_TEXT[a['was']])} -> {tr(mastery.STATE_TEXT[a['state']])}")
        for r in mrep["review"]:
            print(f"  ! {r['name']}: {r['note']}")
        bad = [s for s in mrep["skipped"] if s["status"] in ("unmatched", "not_prime")]
        if bad:
            print("  не сопоставлены: " + ", ".join(s["name"] for s in bad[:30]))

    # what the app will show now
    inv = inventory.load()
    items = inv["items"]
    if args.dry_run and rep and not rep["refused"]:
        # preview the would-be inventory without touching the file
        items = {**({} if rep["mode"] == "replace" else items),
                 **{m["slug"]: 0 for m in rep["matched"]}}
        for m in rep["matched"]:
            items[m["slug"]] = max(items[m["slug"]], m["count"])
    split = analysis.split_inventory(cat, items)
    marks_now = mastery.load()
    print(f"\n=== Итог: разных частей {len(items)}, всего {sum(items.values())} шт.")
    print(f"Полных комплектов: {len(split['complete'])} "
          f"(экземпляров {sum(r['complete'] for r in split['complete'])})")
    for r in split["complete"]:
        st = cat["sets"][r["slug"]]
        state = mastery.state_of(marks_now, r["slug"]) if mastery.masterable(st) else "na"
        warn = "  <-- НЕ ОСВОЕНО" if state == "none" else ""
        print(f"  {st['title']} x{r['complete']}{warn}")
    near = [r for r in split["partial"] if sum(m["count"] for m in r["missing"]) == 1]
    print(f"Не хватает одной части: {len(near)} комплектов; всего начатых: {len(split['partial'])}")
    return 2 if rep and rep["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
