"""The texts of the interface and their translations.

    python tools/i18n_keys.py                 list what is missing or wrong in web/i18n/*.json
    python tools/i18n_keys.py --dump FILE     write every text with the place it is used in (for a translator)
    python tools/i18n_keys.py --prune         drop translations of texts the code no longer has

The texts are written in Russian in the code: t("…") / tn("…|…|…", n) / tx("…") in web/app.js,
{{t:…}} in web/index.html, tr("…") / tn("…") / N_("…") in the Python modules.  A table
web/i18n/<lang>.json maps each of them to its translation.  Rules a translation must keep:
  * the same placeholders {0}, {1}… (in any order);
  * for a text with forms ("# часть|# части|# частей") -- as many forms as the language has plural
    categories (see primesets/i18n.py), each with the # that stands for the number.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from primesets import i18n  # noqa: E402

JS_CALL = re.compile(r'(?<![\w$.])(t|tn|tx)\(\s*"((?:[^"\\]|\\.)*)"')
HTML_KEY = re.compile(r"\{\{t:(.+?)\}\}", re.S)
PLACE = re.compile(r"\{\d+\}")
PY_FUNCS = {"tr": 0, "tn": 0, "N_": 0}


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def collect() -> Dict[str, List[str]]:
    """Every text of the interface -> the places it is used in ("web/app.js:120: the line")."""
    found: Dict[str, List[str]] = {}

    def add(key: str, where: str) -> None:
        key = key.strip()
        if key:
            found.setdefault(key, [])
            if len(found[key]) < 3:
                found[key].append(where)

    js_path = ROOT / "web" / "app.js"
    js = js_path.read_text(encoding="utf-8")
    lines = js.split("\n")
    for m in JS_CALL.finditer(js):
        n = _line(js, m.start())
        add(json.loads('"' + m.group(2) + '"'), f"web/app.js:{n}: {lines[n - 1].strip()[:220]}")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for m in HTML_KEY.finditer(html):
        add(m.group(1), f"web/index.html:{_line(html, m.start())}")
    for path in sorted(list((ROOT / "primesets").rglob("*.py")) + [ROOT / "app.py"]):
        if path.name == "i18n.py":              # the functions themselves: no texts of the interface there
            continue
        src = path.read_text(encoding="utf-8")
        src_lines = src.split("\n")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name not in PY_FUNCS or not node.args:
                continue
            arg = node.args[0]
            rel = path.relative_to(ROOT).as_posix()
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                add(arg.value, f"{rel}:{node.lineno}: {src_lines[node.lineno - 1].strip()[:220]}")
            elif name != "tr" or not _is_passthrough(arg):
                raise SystemExit(f"{rel}:{node.lineno}: the text given to {name}() must be written out as a string")
    return found


def _is_passthrough(arg: ast.AST) -> bool:
    """tr(TABLE[key]) and tr(variable): the text itself is marked with N_() where the table is written."""
    return isinstance(arg, (ast.Subscript, ast.Name, ast.Attribute))


def load(lang: str) -> Dict[str, str]:
    path = ROOT / "web" / "i18n" / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return dict(data.get("strings") or {})


def problems(lang: str, keys: Dict[str, List[str]]) -> Tuple[List[str], List[str], List[str]]:
    """(texts without a translation, translations that break a rule, translations of texts that are gone)."""
    table = load(lang)
    forms = len(i18n.LANGS[lang]["plural"])
    missing = [k for k in keys if not table.get(k, "").strip()]
    wrong = []
    for key, value in table.items():
        if key not in keys or not value.strip():
            continue
        if sorted(set(PLACE.findall(key))) != sorted(set(PLACE.findall(value))):
            wrong.append(f"{key!r}: placeholders differ -> {value!r}")
        if "|" in key and "#" in key:
            parts = value.split("|")
            if len(parts) != forms:
                wrong.append(f"{key!r}: {len(parts)} forms, {lang} needs {forms} -> {value!r}")
            elif not all("#" in part for part in parts):
                wrong.append(f"{key!r}: a form without # -> {value!r}")
        if value != value.strip():
            wrong.append(f"{key!r}: spaces around the translation")
    extra = [k for k in table if k not in keys]
    return missing, wrong, extra


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dump", help="write every text with its context to this JSON file")
    ap.add_argument("--prune", action="store_true", help="remove translations of texts the code no longer has")
    args = ap.parse_args()
    keys = collect()
    out = sys.stdout.buffer
    out.write(f"texts in the code: {len(keys)}\n".encode("utf-8"))
    if args.dump:
        Path(args.dump).write_text(json.dumps([{"key": k, "where": v} for k, v in sorted(keys.items())],
                                              ensure_ascii=False, indent=1), encoding="utf-8")
        out.write(f"written: {args.dump}\n".encode("utf-8"))
    bad = 0
    for lang in i18n.LANGS:
        if lang == i18n.SOURCE:
            continue
        missing, wrong, extra = problems(lang, keys)
        out.write(f"{lang}: {len(load(lang))} translations, missing {len(missing)}, wrong {len(wrong)}, unused {len(extra)}\n".encode("utf-8"))
        for line in wrong[:40]:
            out.write(("   ! " + line + "\n").encode("utf-8"))
        for key in missing[:15]:
            out.write(("   - " + key[:150] + "\n").encode("utf-8"))
        if args.prune and extra:
            path = ROOT / "web" / "i18n" / f"{lang}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["strings"] = {k: v for k, v in data["strings"].items() if k in keys}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            out.write(f"   pruned {len(extra)}\n".encode("utf-8"))
        bad += len(missing) + len(wrong)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
