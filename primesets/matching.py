"""Match item names as they appear in the game to catalog parts.

warframe.market's localized names are the game's own localization, so after normalisation
(case, accents, punctuation, the word for "blueprint") most names match exactly.  Every part is
known under three names -- in the language of the interface, in the language of the game
client and in English -- and a caption may be in any of them.
A cautious fuzzy step catches small reading slips and flags them for review.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .i18n import tr

# the word for "blueprint" and for "set" in the languages of the game (after normalize())
BLUEPRINT_TOKENS = {"чертеж", "blueprint", "blaupause", "schema", "schemat"}
PRIME_TOKENS = {"прайм", "prime"}
SET_TOKENS = {"комплект", "set", "zestaw"}
AND_TOKENS = {"and", "und", "et", "i"}
_NON_WORD = re.compile(r"[^\w]+|_")
_CJK = re.compile(r"([㐀-鿿豈-﫿])")

FUZZY_STRONG = 0.92     # accept on its own
FUZZY_WEAK = 0.84       # accept only with a clear lead over the runner-up
FUZZY_MARGIN = 0.05
# One or two letters misread in the game's stylised font («Нечжа» for «Нэчжа») with no other
# candidate anywhere near: accepted without asking the user to look.
CONFIDENT_SCORE = 0.93
CONFIDENT_MARGIN = 0.08


def normalize(text: str) -> str:
    """Lower case, no punctuation, no accents; "&" and its words become one token.

    Russian letters are kept as they are (only ё -> е), so Russian names give the same keys as
    in the first version of the app.  Chinese has no spaces between words: every character
    becomes a token of its own, and the two-character words for "blueprint" and "set" are
    replaced by the English ones first.
    """
    out = []
    for ch in (text or "").casefold().replace("&", " и "):
        if "Ѐ" <= ch <= "ӿ":
            out.append("е" if ch == "ё" else ch)
            continue
        for piece in unicodedata.normalize("NFKD", ch):
            if not unicodedata.combining(piece):
                out.append(piece)
    s = "".join(out).replace("ł", "l").replace("蓝图", " blueprint ").replace("一套", " set ")
    s = _CJK.sub(r" \1 ", s)
    return " ".join("и" if tok in AND_TOKENS else tok for tok in _NON_WORD.sub(" ", s).split())


def split_blueprint(text: str) -> Tuple[str, bool]:
    """Return (key without the blueprint word, whether the word was present)."""
    tokens = normalize(text).split()
    has_bp = any(t in BLUEPRINT_TOKENS for t in tokens)
    return " ".join(t for t in tokens if t not in BLUEPRINT_TOKENS), has_bp


@dataclass
class Match:
    status: str                    # exact | fuzzy | built | not_prime | unmatched
    slug: Optional[str] = None
    score: float = 0.0
    note: str = ""
    suggestions: List[str] = field(default_factory=list)   # slugs, best first
    confident: bool = True         # False: a fuzzy match the user should look at

    @property
    def ok(self) -> bool:
        return self.status in ("exact", "fuzzy")


def _inexact(score: float) -> str:
    return tr("название прочитано неточно (совпадение {0})", f"{score:.0%}")


class Matcher:
    def __init__(self, catalog: Dict[str, Any]):
        self.parts: Dict[str, dict] = {}
        self._exact: Dict[str, str] = {}
        self._bag: Dict[str, str] = {}
        for st in catalog["sets"].values():
            for part in st["parts"]:
                self.parts[part["slug"]] = part
                for name in (part["name"], part["en"], part.get("game") or ""):
                    key, _ = split_blueprint(name)
                    if not key:
                        continue
                    self._exact.setdefault(key, part["slug"])
                    self._bag.setdefault(" ".join(sorted(key.split())), part["slug"])
        self._keys = list(self._exact)
        # whole items ("Акцельтра Прайм") -> set slug, for mastery marks
        self.sets: Dict[str, dict] = dict(catalog["sets"])
        self._set_exact: Dict[str, str] = {}
        for st in catalog["sets"].values():
            for name in (st["title"], st["title_en"], st.get("title_game") or ""):
                key = self._set_key(name)
                if key:
                    self._set_exact.setdefault(key, st["slug"])

    @staticmethod
    def _set_key(name: str) -> str:
        return " ".join(t for t in normalize(name).split() if t not in BLUEPRINT_TOKENS and t not in SET_TOKENS)

    @staticmethod
    def _rank(key: str, index: Dict[str, str], limit: int = 4) -> List[Tuple[float, str]]:
        """Distinct slugs ordered by similarity of their best key."""
        best: Dict[str, float] = {}
        matcher = difflib.SequenceMatcher(autojunk=False)
        matcher.set_seq2(key)
        for cand, slug in index.items():
            matcher.set_seq1(cand)
            if matcher.real_quick_ratio() < 0.6 or matcher.quick_ratio() < 0.6:
                continue
            ratio = matcher.ratio()
            if ratio > best.get(slug, 0.0):
                best[slug] = ratio
        return sorted(((r, s) for s, r in best.items()), reverse=True)[:limit]

    def _ranked(self, key: str, limit: int = 4) -> List[Tuple[float, str]]:
        return self._rank(key, self._exact, limit)

    def match_set(self, name: str) -> Match:
        """Match the name of a whole item (warframe, weapon, sentinel...) to its prime set."""
        key = self._set_key(name)
        if not key:
            return Match("unmatched", note=tr("пустое название"))
        slug = self._set_exact.get(key)
        if slug:
            return Match("exact", slug=slug, score=1.0)
        if not (set(key.split()) & PRIME_TOKENS):
            return Match("not_prime", note=tr("не прайм-предмет"))
        ranked = self._rank(key, self._set_exact)
        suggestions = [s for _, s in ranked]
        if ranked:
            top, top_slug = ranked[0]
            runner = ranked[1][0] if len(ranked) > 1 else 0.0
            if top >= FUZZY_STRONG or (top >= FUZZY_WEAK and top - runner >= FUZZY_MARGIN):
                sure = top >= CONFIDENT_SCORE and top - runner >= CONFIDENT_MARGIN
                return Match("fuzzy", slug=top_slug, score=top, suggestions=suggestions, confident=sure,
                             note="" if sure else _inexact(top))
        return Match("unmatched", note=tr("нет такого прайм-предмета в каталоге"), suggestions=suggestions,
                     score=ranked[0][0] if ranked else 0.0)

    def match(self, name: str, blueprint: Optional[bool] = None) -> Match:
        key, bp_in_name = split_blueprint(name)
        if not key:
            return Match("unmatched", note=tr("пустое название"))
        is_bp: Optional[bool] = True if bp_in_name else blueprint

        slug = self._exact.get(key) or self._bag.get(" ".join(sorted(key.split())))
        status, score, sure = "exact", 1.0, True
        suggestions: List[str] = []
        if slug is None:
            if not (set(key.split()) & PRIME_TOKENS):
                return Match("not_prime", note=tr("не прайм-часть"))
            ranked = self._ranked(key)
            suggestions = [s for _, s in ranked]
            if ranked:
                top, top_slug = ranked[0]
                runner = ranked[1][0] if len(ranked) > 1 else 0.0
                if top >= FUZZY_STRONG or (top >= FUZZY_WEAK and top - runner >= FUZZY_MARGIN):
                    slug, status, score = top_slug, "fuzzy", top
                    sure = top >= CONFIDENT_SCORE and top - runner >= CONFIDENT_MARGIN
            if slug is None:
                return Match("unmatched", note=tr("нет такого названия в каталоге"), suggestions=suggestions,
                             score=ranked[0][0] if ranked else 0.0)

        part = self.parts[slug]
        note = ""
        if part["blueprint"] and is_bp is False:
            return Match("built", slug=slug, score=score,
                         note=tr("это не чертёж, а уже построенный предмет — в комплект для продажи не идёт"))
        if part["blueprint"] and is_bp is None:
            note = tr("в названии нет слова «чертёж» — считаю чертежом")
        elif not part["blueprint"] and is_bp and not bp_in_name:
            # the foundry lists every card as a blueprint, but a weapon part needs none: nothing to report
            note = ""
        elif not part["blueprint"] and is_bp:
            note = tr("распознано как чертёж, но у этой части чертежа не бывает")
        if status == "fuzzy" and not sure:
            note = _inexact(score) + ("; " + note if note else "")
        return Match(status, slug=slug, score=score, note=note, suggestions=suggestions, confident=sure)
