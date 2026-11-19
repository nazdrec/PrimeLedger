"""Interface languages.

The texts of the app are written in Russian in the code and looked up in the table of the
chosen language: web/i18n/<lang>.json, {"strings": {"<Russian text>": "<translation>"}}.
The same tables serve the page (they are handed over as window.I18N) and this module.

    tr("Справочник ещё не загружен")              a plain text
    tr("В хранилище {0} из {1} частей", 2, 4)     {0}, {1} are filled in
    tn("# часть|# части|# частей", 5)             depends on a number; # is the number itself
    N_("Варфрейм")                                marks a text of a constant table for the
                                                  key list; translate it with tr() when used

A text without a translation is shown as it is written, in Russian: tools/i18n_keys.py and
the tests make sure no table has gaps.
"""
from __future__ import annotations

import html
import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional

from . import APP_NAME, config

log = logging.getLogger("primesets")

DEFAULT = "en"          # for a system language the app has no table for
SOURCE = "ru"           # the language the texts are written in
# name     -- how the language calls itself
# locale   -- for number and date formats on the page
# wfm      -- the code warframe.market uses for this language (item names, site address)
# plural   -- the order of the forms in tn() texts, as CLDR names the categories
# lang_id  -- the primary language number Windows reports for the interface language
LANGS: Dict[str, Dict[str, Any]] = {
    "ru": {"name": "Русский", "locale": "ru-RU", "wfm": "ru", "plural": ["one", "few", "many"], "lang_id": 0x19},
    "en": {"name": "English", "locale": "en-US", "wfm": "en", "plural": ["one", "other"], "lang_id": 0x09},
    "de": {"name": "Deutsch", "locale": "de-DE", "wfm": "de", "plural": ["one", "other"], "lang_id": 0x07},
    "fr": {"name": "Français", "locale": "fr-FR", "wfm": "fr", "plural": ["one", "other"], "lang_id": 0x0C},
    "pl": {"name": "Polski", "locale": "pl-PL", "wfm": "pl", "plural": ["one", "few", "many"], "lang_id": 0x15},
    "zh": {"name": "简体中文", "locale": "zh-CN", "wfm": "zh-hans", "plural": ["other"], "lang_id": 0x04},
}

_lock = threading.Lock()
_tables: Dict[str, Dict[str, str]] = {}
_current = SOURCE


def valid(lang: Any) -> bool:
    return isinstance(lang, str) and lang in LANGS


def system_language() -> str:
    """The language Windows shows its own interface in, if the app speaks it."""
    try:
        import ctypes
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        for code, info in LANGS.items():
            if info["lang_id"] == primary:
                return code
    except Exception:
        pass
    try:
        import locale
        code = (locale.getlocale()[0] or "")[:2].lower()
        if code in LANGS:
            return code
    except Exception:
        pass
    return DEFAULT


def table(lang: str) -> Dict[str, str]:
    """The translations of one language ({} for Russian and for a missing or broken file)."""
    if lang == SOURCE or not valid(lang):
        return {}
    with _lock:
        hit = _tables.get(lang)
        if hit is not None:
            return hit
        strings: Dict[str, str] = {}
        try:
            data = json.loads((config.WEB_DIR / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
            raw = data.get("strings") if isinstance(data, dict) else None
            if isinstance(raw, dict):
                strings = {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v}
        except (OSError, ValueError):
            log.warning("no translation table for %s", lang)
        _tables[lang] = strings
        return strings


def forget_tables() -> None:
    with _lock:
        _tables.clear()


def set_language(lang: str) -> str:
    global _current
    _current = lang if valid(lang) else DEFAULT
    return _current


def current() -> str:
    return _current


def info(lang: Optional[str] = None) -> Dict[str, Any]:
    return LANGS[lang if valid(lang) else _current]


def _lookup(text: str, lang: Optional[str] = None) -> str:
    """The translation with the spaces the code put around the text kept as they were."""
    key = text.strip()
    hit = table(lang or _current).get(key)
    if hit is None:
        return text
    lead = text[:len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()):]
    return lead + hit + tail


_PLACE = re.compile(r"\{(\d+)\}")


def _fill(text: str, args: tuple) -> str:
    if not args:
        return text
    return _PLACE.sub(lambda m: str(args[int(m.group(1))]) if int(m.group(1)) < len(args) else "", text)


def tr(text: str, *args: Any, lang: Optional[str] = None) -> str:
    return _fill(_lookup(text, lang), args)


def N_(text: str) -> str:  # noqa: N802 - the conventional name of a "translate later" mark
    return text


def plural_category(lang: str, n: Any) -> str:
    """CLDR plural category of a whole number -- the same answer Intl.PluralRules gives on the page."""
    try:
        whole = float(n) == int(n)
        n = abs(int(n))
    except (TypeError, ValueError, OverflowError):
        return "other"
    if not whole:
        return "other"
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "pl":
        if n == 1:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "fr":
        return "one" if n in (0, 1) else "other"
    if lang == "zh":
        return "other"
    return "one" if n == 1 else "other"


def group(n: Any, lang: Optional[str] = None) -> str:
    """12345 the way the language writes it."""
    try:
        text = f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)
    lang = lang or _current
    if lang in ("ru", "fr", "pl"):
        return text.replace(",", " ")
    if lang == "de":
        return text.replace(",", ".")
    return text


def tn(forms: str, n: Any, *args: Any, lang: Optional[str] = None) -> str:
    lang = lang or _current
    text = _lookup(forms, lang)
    # a text without a translation is still Russian: its forms follow the Russian rule
    rule = SOURCE if (lang != SOURCE and text == forms) else lang
    options = text.split("|")
    order: List[str] = LANGS[rule]["plural"]
    cat = plural_category(rule, n)
    idx = order.index(cat) if cat in order else len(options) - 1
    idx = min(idx, len(options) - 1)
    return _fill(options[idx].replace("#", group(n, lang)), args)


# --------------------------------------------------------------------------- for the page
def page_table(lang: Optional[str] = None) -> Dict[str, Any]:
    lang = lang if valid(lang) else _current
    meta = LANGS[lang]
    return {"lang": lang, "locale": meta["locale"], "plural": meta["plural"], "wfm": meta["wfm"],
            "name": meta["name"], "app": APP_NAME, "strings": table(lang),
            "languages": [{"code": code, "name": item["name"]} for code, item in LANGS.items()]}


def page_script(lang: Optional[str] = None) -> str:
    """What /i18n.js serves: the table of the current language as a global the page reads."""
    # "</" must not appear inside a script: a translation could hold it
    body = json.dumps(page_table(lang), ensure_ascii=False).replace("</", "<\\/")
    return "window.I18N = " + body + ";\n"


_HTML_KEY = re.compile(r"\{\{t:(.+?)\}\}", re.S)


def render_html(text: str, lang: Optional[str] = None) -> str:
    """Fill {{t:Русский текст}} and {{app}} in the page's HTML and set its lang attribute."""
    lang = lang if valid(lang) else _current
    text = _HTML_KEY.sub(lambda m: html.escape(tr(m.group(1), lang=lang), quote=True), text)
    text = text.replace("{{app}}", html.escape(APP_NAME))
    return text.replace("{{lang}}", LANGS[lang]["locale"].split("-")[0] if lang != "zh" else "zh-Hans")
