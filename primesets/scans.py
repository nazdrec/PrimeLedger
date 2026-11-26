"""Reading two more kinds of screenshots: the list of riven mods and the list of void relics.

They go the same way as the screenshots of the inventory (recognize.py) -- the connection chosen
in the settings reads one screenshot at a time, the answer is parsed as JSON and checked, nothing
in it is executed -- but each kind has an inbox folder, a request and a result of its own, so the
reading of the prime parts, which was verified on real screenshots, is left exactly as it was.

The app still never touches the game: the input is picture files the user made.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import analysis, config, i18n, providers, relics, rivens, settings, shots
from .i18n import tr
from .providers import ProviderError, Task
from .recognize import GAME_LANGUAGE, NOTES_LANGUAGE, SYSTEM_ATTACHED, SYSTEM_FILES, not_ready

log = logging.getLogger("primesets")

KINDS = ("rivens", "relics")
MAX_FILES = 60                       # of one reading: a long list of relics takes a dozen screens or two


def inbox(kind: str) -> Path:
    """Where the screenshots of this kind wait to be read (a folder next to the inventory's inbox)."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind of screenshots: {kind}")
    return config.SCREENSHOT_DIR / f"_{kind}"


def files(kind: str) -> List[Path]:
    folder = inbox(kind)
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in shots.EXT)


def find(kind: str, name: str) -> Optional[Path]:
    """A screenshot by its file name -- only from the inbox of this kind, never a path."""
    for f in files(kind):
        if f.name == name:
            return f
    return None


# --------------------------------------------------------------------------- the answers
def _schema(screen: str, item: Dict[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {"screen": {"type": "string", "enum": [screen, "other"]}}
    props["items"] = {"type": "array", "items": {"type": "object", "properties": item, "required": list(item),
                                                 "additionalProperties": False}}
    props["notes"] = {"type": "string"}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SCHEMAS: Dict[str, Dict[str, Any]] = {
    "rivens": _schema("rivens", {"name": {"type": "string"}}),
    "relics": _schema("relics", {
        "name": {"type": "string"},
        "refinement": {"type": "string", "enum": list(analysis.REFINEMENTS)},
        "count": {"type": "integer"},
        "count_visible": {"type": "boolean"},
    }),
}

# --------------------------------------------------------------------------- the requests, Russian client
# Both descriptions were written from real screenshots of the Russian client (2026-11) and checked on them.
# Relics are read from the sell screen of the inventory (the "Relics" category) -- the same screen the prime
# parts are shot on; the first draft read the refinement segment of the orbiter, the user asked for this one.
RU_HEAD_FILES = """В текущей папке лежат фрагменты ОДНОГО скриншота игры Warframe (фрагменты частично перекрываются):
{files}

Прочитай каждый файл инструментом Read и выпиши [WHAT].
Просто перепиши то, что видно: выводов не делай.
"""
RU_HEAD_ATTACHED = """К сообщению приложены фрагменты ОДНОГО скриншота игры Warframe (фрагменты частично перекрываются; порядок — слева направо, сверху вниз).

Выпиши [WHAT].
Просто перепиши то, что видно: выводов не делай.
"""
RU_TAIL = """
ДЛЯ ЛЮБОГО ЭКРАНА:
  - то, что обрезано краем фрагмента, пропусти: оно целиком видно на соседнем фрагменте;
  - одно и то же, видимое на двух фрагментах, запиши один раз;
  - если подпись не читается уверенно, не угадывай: пропусти её и напиши о ней в notes.

notes — только то, что прочитать НЕ удалось: какая подпись или число и где это на экране.
  Если всё прочитано — пустая строка. Не описывай ход работы, перекрытие фрагментов и пропущенные дубликаты.
"""
RU_WHAT = {"rivens": "моды Разлома — карточки модов в фиолетовой рамке", "relics": "реликвии Бездны — плитки списка реликвий"}
RU_BODY = {
    "rivens": """
screen — какой это экран:
  rivens — на экране есть карточки модов Разлома;
  other  — их нет.

items — по одной записи на каждую карточку мода Разлома.
Как выглядит карточка: широкая фиолетовая рамка с острыми краями, в правом верхнем углу число со значком
полярности, в середине подпись в одну или две строки. В подписи сначала название оружия, затем имя мода —
одно слово, часто с дефисом: «Ангстрем Mantican», «Жнец Прайм Crita-ignitox», «Посланник Догмат Manti-acrican».
Имя мода обычно написано латиницей, но часть его бывает кириллицей («Пила Упыря форти-critatox»,
«Меч Панголин Hexa-лациум») — переписывай буква в букву, как на экране.
  name   подпись целиком: название оружия и имя мода, ровно как написано, без исправлений и перевода.
         Строки соедини пробелом; но если строка кончается дефисом, продолжение со следующей строки припиши
         сразу после дефиса, без пробела («Crita-» и «ignitox» → «Crita-ignitox»).
         Число в углу карточки и значки в подпись не входят.
  Карточку, в подписи которой нет названия оружия (завуалированный мод Разлома), пропусти.
  Обычные моды — карточки не в фиолетовой рамке Разлома — пропусти и в notes о них не пиши.
  Ряд карточек, обрезанный краем списка так, что подписи видны не целиком, пропусти и в notes о нём не пиши.
""",
    "relics": """
screen — какой это экран:
  relics — список реликвий Бездны: сетка квадратных плиток, на каждой картинка реликвии и подпись вида
           «Реликвия Нео A13» (в игре это экран «ИНВЕНТАРЬ / ПРОДАТЬ», категория «РЕЛИКВИИ»);
  other  — что-то другое.

items — по одной записи на каждую плитку реликвии.
На плитке: картинка реликвии, внизу подпись в 1–3 строки («Реликвия Акси A22», «Реликвия Нео F3 [Сияющая]»),
в левом верхнем углу может стоять число рядом с галочкой в кружке — это количество.
  name           подпись целиком, строки соедини пробелом; ровно как написано, вместе со словом в квадратных
                 скобках, если оно есть. Букву и число в коде реликвии («A13», «K9») переписывай особенно
                 внимательно.
  refinement     степень улучшения — по слову в квадратных скобках в конце подписи:
                   intact      — скобок нет;
                   exceptional — [Необычная];
                   flawless    — [Бесподобная];
                   radiant     — [Сияющая].
  count          число в левом верхнем углу плитки, рядом с галочкой в кружке (на другом экране игры оно
                 написано после «x»); если числа нет — 1.
  count_visible  true, если число было на плитке; false, если ты поставил 1, потому что числа нет.
  Нижний ряд плиток, у которых подписи обрезаны краем экрана, пропусти и в notes о нём не пиши.
""",
}

# --------------------------------------------------------------------------- the requests, any other client
# The same for a game client in another language: the screens are described by what they look like.
EN_HEAD_FILES = """The current folder holds the pieces of ONE screenshot of the game Warframe (the pieces partly overlap):
{files}

Read every file with the Read tool and list [WHAT].
"""
EN_HEAD_ATTACHED = """Attached are the pieces of ONE screenshot of the game Warframe (they partly overlap; the order is left to right, top to bottom).

List [WHAT].
"""
EN_LEAD = """The game client is in LANGUAGE: copy every caption exactly as it is written, in that language.
Do not translate, do not correct, do not draw conclusions.
"""
EN_TAIL = """
FOR ANY SCREEN:
  - skip what is cut off by the edge of a piece: it is whole on the neighbouring piece;
  - write what is visible on two pieces once;
  - if a caption cannot be read with confidence, do not guess: skip it and mention it in notes.

notes - only what could NOT be read: which caption or number and where on the screen.
  If everything was read - an empty string. Do not describe the course of the work, the overlap of the pieces
  or skipped duplicates.
"""
EN_WHAT = {"rivens": "the Riven mods: the mod cards in a purple frame", "relics": "the Void Relics: the tiles of the relic list"}
EN_BODY = {
    "rivens": """
screen - which screen this is:
  rivens - the screenshot shows cards of Riven mods;
  other  - it does not.

items - one entry for each card of a Riven mod.
What a card looks like: a wide purple frame with sharp edges, a number with a polarity icon in its top right
corner, and a caption of one or two lines in the middle. The caption is the name of a weapon followed by the
mod's own name - one word, often with a hyphen (in the English client: "Angstrum Mantican",
"Reaper Prime Crita-ignitox").
  name   the whole caption: the weapon and the mod's own name, exactly as written.
         Join the lines with a space; but when a line ends with a hyphen, put what follows on the next line
         right after the hyphen, with no space ("Crita-" and "ignitox" -> "Crita-ignitox").
         The number in the corner of the card and the icons are not part of the caption.
  Skip a card whose caption names no weapon (a veiled Riven mod).
  Skip ordinary mods - cards without the purple Riven frame - and do not mention them in notes.
  Skip a row of cards cut off by the edge of the list so that the captions are not whole; do not mention it in notes.
""",
    "relics": """
screen - which screen this is:
  relics - a list of Void Relics: a grid of square tiles, each with the picture of a relic and a caption under it
           (in the game it is the Inventory / Sell screen with the Relics category chosen);
  other  - anything else.

items - one entry for each relic tile.
On a tile: the picture of a relic, at the bottom a caption of 1-3 lines - the word for "relic", its era (Lith,
Meso, Neo, Axi or Requiem) and its code such as A13 (in the English client: "Lith A13 Relic") - sometimes
followed by a word in square brackets that names the refinement; in the top left corner there may be a number
next to a check mark in a circle: that is the count.
  name           the whole caption, lines joined with a space, exactly as written, together with the bracketed
                 word if there is one. Copy the letter and the number of the relic's code ("A13", "K9") with
                 special care.
  refinement     the refinement the bracketed word at the end of the caption names:
                   intact      - no brackets (or the word for "intact");
                   exceptional - the first step of refinement;
                   flawless    - the second step;
                   radiant     - the last and best step
                 (in the English client: [Exceptional], [Flawless], [Radiant]).
  count          the number in the top left corner of the tile, next to the check mark in a circle (on another
                 screen of the game it follows an "x"); 1 when there is no number.
  count_visible  true if the number was on the tile; false if you put 1 because there is no number.
  Skip the bottom row of tiles whose captions are cut off by the edge of the screen; do not mention it in notes.
""",
}


def task(kind: str, game_lang: Optional[str] = None, ui_lang: Optional[str] = None) -> Task:
    """The request for one screenshot of this kind, for a client in the given language."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind of screenshots: {kind}")
    game_lang = game_lang if game_lang in GAME_LANGUAGE else settings.game_language()
    ui_lang = ui_lang if ui_lang in NOTES_LANGUAGE else i18n.current()
    if game_lang == "ru":
        body = RU_BODY[kind] + RU_TAIL
        if ui_lang != "ru":
            body += f"\nWrite the notes field in {NOTES_LANGUAGE[ui_lang]}.\n"
        return Task(SYSTEM_FILES, SYSTEM_ATTACHED, RU_HEAD_FILES.replace("[WHAT]", RU_WHAT[kind]) + body,
                    RU_HEAD_ATTACHED.replace("[WHAT]", RU_WHAT[kind]) + body, SCHEMAS[kind])
    body = EN_LEAD.replace("LANGUAGE", GAME_LANGUAGE[game_lang][0]) + EN_BODY[kind] + EN_TAIL
    body += f"\nWrite the notes field in {NOTES_LANGUAGE[ui_lang]}.\n"
    return Task(SYSTEM_FILES, SYSTEM_ATTACHED, EN_HEAD_FILES.replace("[WHAT]", EN_WHAT[kind]) + body,
                EN_HEAD_ATTACHED.replace("[WHAT]", EN_WHAT[kind]) + body, SCHEMAS[kind])


def clean_answer(kind: str, data: Any) -> Dict[str, Any]:
    """A model's answer brought to the shape of the schema, whatever the model made of it: wrong types
    become the harmless default and unknown fields are dropped."""
    if not isinstance(data, dict) or ("items" not in data and "screen" not in data):
        raise ProviderError(tr("В ответе нет данных в нужном формате: {0}", json.dumps(data, ensure_ascii=False)[:300]),
                            "bad_output")
    items = []
    for it in data.get("items") if isinstance(data.get("items"), list) else []:
        if not isinstance(it, dict):
            continue
        name = " ".join(str(it.get("name") or "").split())[:160]
        if not name:
            continue
        if kind == "rivens":
            items.append({"name": name})
            continue
        try:
            count = int(it.get("count") or 1)
        except (TypeError, ValueError):
            count = 1
        items.append({"name": name, "refinement": it.get("refinement") if it.get("refinement") in analysis.REFINEMENTS else None,
                      "count": max(1, min(relics.MAX_COUNT, count)), "count_visible": it.get("count_visible") is True})
    return {"screen": kind if data.get("screen") == kind else "other", "items": items,
            "notes": str(data.get("notes") or "").strip()}


# --------------------------------------------------------------------------- one reading
class ScanJob:
    """One reading of the screenshots that were in the inbox of a kind when it started.

    context() gives what the captions are matched against: rivens.Weapons or relics.Index.  It is
    asked for once, before the first screenshot is read, so that a market that does not answer
    stops the reading before the user's subscription is spent on it.
    """

    def __init__(self, kind: str, paths: List[Path], context: Callable[[], Any]):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.files = [{"name": f.name, "path": f, "state": "queued", "found": 0, "error": "", "screen": ""}
                      for f in paths[:MAX_FILES]]
        self.state = "running"          # running | review | applied | error | cancelled
        self.error = ""
        self.error_code = ""
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.review: Optional[Dict[str, Any]] = None
        self.notes: List[str] = []
        self._context = context
        self._cancel = threading.Event()
        self._procs: list = []
        self._lock = threading.Lock()
        self._results: List[Dict[str, Any]] = []
        self._work = Path(tempfile.mkdtemp(prefix="primesets-"))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            data: Dict[str, Any] = {
                "id": self.id, "kind": self.kind, "state": self.state, "error": self.error, "error_code": self.error_code,
                "files": [{k: f[k] for k in ("name", "state", "found", "error", "screen")} for f in self.files],
                "done": sum(1 for f in self.files if f["state"] in ("done", "error")),
                "total": len(self.files),
                "seconds": round((self.finished_at or time.time()) - self.started_at),
            }
            if self.state == "review" and self.review is not None:
                data["review"] = self.review
                data["notes"] = self.notes
            return data

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            if self.state == "running":
                self.state = "cancelled"
                self.finished_at = time.time()
        for proc in list(self._procs):
            try:
                proc.kill()
            except OSError:
                pass
        self.cleanup()

    def cleanup(self) -> None:
        shutil.rmtree(self._work, ignore_errors=True)

    def run(self) -> None:
        try:
            provider = providers.current()
            status = provider.status()
            if not status["ready"]:
                status = provider.status(force=True)     # a remembered "not signed in" may be out of date
            if not status["ready"]:
                raise not_ready(status)
            try:
                context = self._context()
            except Exception as exc:     # no list of names to match the captions against: nothing is read
                raise ProviderError(tr("warframe.market не ответил, а без его списка названий подписи не с чем сверить: {0}",
                                       exc), "network") from None
            job_task = task(self.kind)
            queue = list(range(len(self.files)))
            fatal: List[ProviderError] = []

            def worker() -> None:
                while not self._cancel.is_set() and not fatal:
                    with self._lock:
                        if not queue:
                            return
                        idx = queue.pop(0)
                        entry = self.files[idx]
                        entry["state"] = "reading"
                    try:
                        tiles = shots.make_tiles(entry["path"], self._work / f"shot{idx:03d}")
                        answer = provider.read(tiles[0].parent, tiles, job_task, holder=self._procs)
                        res = clean_answer(self.kind, answer["data"])
                        res["shot"] = entry["name"]
                        with self._lock:
                            self._results.append(res)
                            entry.update({"state": "done", "found": len(res["items"]), "screen": res["screen"]})
                    except ProviderError as exc:
                        with self._lock:
                            entry.update({"state": "error", "error": str(exc)})
                        if exc.code in providers.FATAL:
                            fatal.append(exc)      # no point in trying the rest
                    except ValueError as exc:      # not a picture: say so, go on with the others
                        with self._lock:
                            entry.update({"state": "error", "error": str(exc)})
                    except Exception as exc:  # one bad screenshot must not stop the batch
                        log.exception("reading failed for %s", entry["name"])
                        with self._lock:
                            entry.update({"state": "error", "error": str(exc)})

            threads = [threading.Thread(target=worker, daemon=True) for _ in range(settings.parallel())]
            for worker_thread in threads:
                worker_thread.start()
            for worker_thread in threads:
                worker_thread.join()
            if self._cancel.is_set():
                return
            if fatal:
                raise fatal[0]
            if not self._results:
                first = next((f["error"] for f in self.files if f["error"]), "")
                raise ProviderError(tr("Ни один скриншот прочитать не удалось: {0}", first) if first
                                    else tr("Ни один скриншот прочитать не удалось"), "nothing")
            order = {f["name"]: i for i, f in enumerate(self.files)}
            self._results.sort(key=lambda r: order.get(r["shot"], 0))
            review = combine(self.kind, self._results, context)
            with self._lock:
                self.review = review
                self.notes = [f"{r['shot']}: {r['notes']}" for r in self._results if r["notes"]]
                self.state = "review"
                self.finished_at = time.time()
        except ProviderError as exc:
            with self._lock:
                self.state, self.error, self.error_code = "error", str(exc), exc.code
                self.finished_at = time.time()
        except Exception as exc:
            log.exception("reading of %s failed", self.kind)
            with self._lock:
                self.state, self.error, self.error_code = "error", str(exc), "error"
                self.finished_at = time.time()
        finally:
            self.cleanup()

    def apply(self, mode: str, skip: Optional[List[int]] = None) -> Dict[str, Any]:
        """Write the reading into the list of its kind.  skip -- the lines the user took out of it."""
        with self._lock:
            if self.state != "review" or self.review is None:
                raise ProviderError(tr("Нет результата распознавания, который можно занести"), "state")
            review = self.review
        left_out = set(skip or [])
        entries = [e for n, e in enumerate(review["entries"]) if n not in left_out]
        found = "weapon" if self.kind == "rivens" else "relic"
        unknown = [e["caption"] for e in entries if not e.get(found)]
        mode = "merge" if mode == "merge" else "replace"
        if self.kind == "rivens":
            rivens.store([{"weapon": e["weapon"], "name": e["name"]} for e in entries if e["weapon"]], unknown, mode)
        else:
            relics.store([{"relic": e["relic"], "refinement": e["refinement"], "count": e["count"]}
                          for e in entries if e["relic"]], unknown, mode)
        archived = shots.archive([f["path"] for f in self.files], label=self.kind)
        with self._lock:
            self.state = "applied"
        return {"archived_to": str(archived) if archived else "", "mode": mode}


def combine(kind: str, per_shot: List[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    """What the screenshots of one reading say together (rivens.review / relics.review), with a word on
    the screenshots that showed something else."""
    captions = [{**it, "shot": shot["shot"]} for shot in per_shot if shot["screen"] == kind for it in shot["items"]]
    review = rivens.review(captions, context) if kind == "rivens" else relics.review(captions, context)
    review["other_screens"] = [shot["shot"] for shot in per_shot if shot["screen"] != kind]
    return review
