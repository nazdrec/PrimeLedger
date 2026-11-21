"""Offline tests of the settings, the key store, the languages and the six ways of reading a screenshot.

No request leaves this computer: the web APIs are played by a small server started here, the
command-line programs by tests/fake_claude.py and tests/fake_codex.py.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import test_core  # noqa: E402,F401  (sets the throw-away data folders before the app is imported)
from test_core import FAKE_CLAUDE, _TMP, make_catalog  # noqa: E402

from primesets import catalog, i18n, inventory, mastery, providers, recognize, settings, shots, vault  # noqa: E402
from primesets.matching import Matcher, normalize, split_blueprint  # noqa: E402
from primesets.providers import ProviderError, codex_cli  # noqa: E402
from primesets.providers.anthropic_api import sdk as anthropic_sdk  # noqa: E402

FAKE_CODEX = [sys.executable, str(Path(__file__).resolve().parent / "fake_codex.py")]
ANSWER = {"screen": "inventory", "notes": "", "items": [
    {"name": "Васто Прайм: Ствол", "rank": None, "count": 2, "count_visible": True, "cut_top": False,
     "blueprint_word": False, "mastered_label": None, "owned_label": None}]}
KEY = "test-key-0123456789abcdef"


def reset_settings():
    for f in (settings.SETTINGS_FILE, vault.SECRETS_FILE):
        if f.exists():
            f.unlink()
    settings._cache.update({"mtime": None, "data": None})
    i18n.set_language("ru")


# --------------------------------------------------------------------------- a stand-in for the web APIs
class FakeApi:
    """Answers like the documented endpoints and remembers what it was asked."""

    def __init__(self):
        self.requests = []
        self.plan = []                   # what to answer next: (status, body); empty -> the normal answer
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, body):
                raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else None
                outer.requests.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
                if outer.plan:
                    status, answer = outer.plan.pop(0)
                    return self._reply(status, answer)
                text = json.dumps(ANSWER, ensure_ascii=False)
                path = self.path.split("?")[0]
                if path.endswith("/responses"):                      # OpenAI
                    return self._reply(200, {"id": "resp_1", "status": "completed", "output": [
                        {"type": "reasoning", "summary": []},
                        {"type": "message", "role": "assistant", "status": "completed",
                         "content": [{"type": "output_text", "text": text, "annotations": []}]}]})
                if path.endswith("/chat/completions"):               # DeepSeek
                    return self._reply(200, {"choices": [{"index": 0, "finish_reason": "stop",
                                                          "message": {"role": "assistant", "content": text}}]})
                if path.endswith("/interactions"):                   # Gemini
                    return self._reply(200, {"id": "i1", "object": "interaction", "status": "completed", "steps": [
                        {"type": "thought", "content": []},
                        {"type": "model_output", "content": [{"type": "text", "text": text}]}]})
                if path.endswith("/v1/messages"):                    # Anthropic
                    return self._reply(200, {"id": "msg_1", "type": "message", "role": "assistant",
                                             "model": (body or {}).get("model", "claude-opus-5-5"),
                                             "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                                             "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}})
                if path.endswith("/models"):
                    if "x-goog-api-key" in {k.lower() for k in self.headers}:
                        return self._reply(200, {"models": [{"name": "models/gemini-4-hydrogen"}, {"name": "models/gemini-embedding-1"}]})
                    return self._reply(200, {"data": [{"id": "gpt-6.2-astra"}, {"id": "gpt-image-2"}, {"id": "deepseek-flash"}]})
                return self._reply(404, {"error": {"message": "no such path"}})

            do_GET = do_POST = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        reset_settings()
        self.work = Path(_TMP.name) / "work"
        self.work.mkdir(exist_ok=True)
        self.tile = self.work / "shot__r1c1.png"
        self.tile.write_bytes(test_core.Recognition.tiny_png())
        self.task = recognize.task("ru", "ru")

    def tearDown(self):
        reset_settings()


# --------------------------------------------------------------------------- settings and keys
class Settings(Base):
    def test_defaults_and_validation(self):
        conf = settings.load()
        self.assertEqual((conf["provider"], conf["language"], conf["game_language"], conf["parallel"]), ("claude_cli", "", "", 3))
        self.assertIn(settings.language(), i18n.LANGS)
        settings.save({"language": "de", "provider": "gemini_api", "parallel": 99, "models": {"gemini_api": " gemini-x ", "nope": "x"}})
        conf = settings.load()
        self.assertEqual((conf["language"], conf["provider"], conf["parallel"], conf["models"]), ("de", "gemini_api", 4, {"gemini_api": "gemini-x"}))
        self.assertEqual((settings.language(), settings.game_language()), ("de", "de"), "the game speaks the interface language unless told")
        settings.save({"game_language": "zh", "language": "klingon", "provider": "hal9000", "models": {"gemini_api": ""}})
        conf = settings.load()
        self.assertEqual((conf["language"], conf["provider"], conf["game_language"], conf["models"]), ("", "claude_cli", "zh", {}))

    def test_hand_made_keys_survive_and_old_names_are_read(self):
        settings.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        settings.SETTINGS_FILE.write_text(json.dumps({"claude_path": "C:/x/claude.exe", "recognize_model": "opus",
                                                      "recognize_parallel": 2}), encoding="utf-8")
        settings._cache.update({"mtime": None, "data": None})
        self.assertEqual((settings.model("claude_cli"), settings.parallel(), settings.extra("claude_path")), ("opus", 2, "C:/x/claude.exe"))
        settings.save({"use_proxy": {"codex_cli": True}})
        raw = json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8"))
        self.assertEqual((raw["claude_path"], raw["models"], raw["use_proxy"]), ("C:/x/claude.exe", {"claude_cli": "opus"}, ["codex_cli"]))
        self.assertTrue(settings.proxied("codex_cli") and not settings.proxied("claude_cli"))


@unittest.skipUnless(vault.available(), "the key store needs Windows")
class Vault(Base):
    def test_a_key_is_stored_encrypted_and_never_shown(self):
        vault.put("openai_api", KEY)
        raw = vault.SECRETS_FILE.read_text(encoding="utf-8")
        self.assertNotIn(KEY, raw)
        self.assertNotIn(KEY[-8:], raw)
        self.assertEqual((vault.get("openai_api"), vault.source("openai_api"), vault.hint("openai_api")), (KEY, "saved", "…cdef"))
        status = providers.get("openai_api").status()
        self.assertTrue(status["ready"] and status["has_key"])
        self.assertNotIn(KEY, json.dumps(status))
        vault.put("openai_api", "")
        self.assertEqual((vault.get("openai_api"), providers.get("openai_api").status()["reason"]), ("", "no_key"))

    def test_a_key_from_the_environment_is_used_but_not_copied(self):
        os.environ["GEMINI_API_KEY"] = KEY
        try:
            self.assertEqual((vault.get("gemini_api"), vault.source("gemini_api")), (KEY, "env"))
            self.assertFalse(vault.SECRETS_FILE.exists())
        finally:
            del os.environ["GEMINI_API_KEY"]
        self.assertEqual(vault.get("gemini_api"), "")

    def test_a_broken_file_reads_as_no_keys(self):
        vault.SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        vault.SECRETS_FILE.write_text(json.dumps({"items": {"openai_api": "bm90IGEgYmxvYg=="}}), encoding="utf-8")
        self.assertEqual(vault.get("openai_api"), "")

    def test_proxy_address(self):
        self.assertEqual(vault.check_proxy(" 10.0.0.1:8080 "), "http://10.0.0.1:8080")
        self.assertEqual(vault.check_proxy("http://me:secret@proxy.example:3128/"), "http://me:secret@proxy.example:3128")
        for bad in ("socks5://10.0.0.1:1080", "http://", "http://host:port"):
            with self.assertRaises(ValueError, msg=bad):
                vault.check_proxy(bad)
        vault.put(vault.PROXY, vault.check_proxy("http://me:secret@proxy.example:3128"))
        self.assertEqual(vault.proxy_hint(), "http://proxy.example:3128 (+ login)")
        self.assertNotIn("secret", vault.proxy_hint())
        self.assertIsNone(vault.proxy_for("openai_api"), "a proxy is used only where it was switched on")
        settings.save({"use_proxy": {"openai_api": True}})
        self.assertEqual(vault.proxy_for("openai_api"), "http://me:secret@proxy.example:3128")


# --------------------------------------------------------------------------- languages
class Languages(Base):
    def test_plural_rules(self):
        cat = i18n.plural_category
        self.assertEqual([cat("ru", n) for n in (1, 2, 5, 11, 21, 22, 25, 111)], ["one", "few", "many", "many", "one", "few", "many", "many"])
        self.assertEqual([cat("pl", n) for n in (1, 2, 5, 12, 21, 22, 25)], ["one", "few", "many", "many", "many", "few", "many"])
        self.assertEqual([cat("en", n) for n in (0, 1, 2)], ["other", "one", "other"])
        self.assertEqual([cat("fr", n) for n in (0, 1, 2)], ["one", "one", "other"])
        self.assertEqual(cat("zh", 1), "other")

    def test_russian_needs_no_table_and_a_missing_text_stays_russian(self):
        self.assertEqual(i18n.tr("нет данных"), "нет данных")
        self.assertEqual(i18n.tn("# часть|# части|# частей", 3), "3 части")
        self.assertEqual(i18n.tn("# часть|# части|# частей", 1234, lang="ru"), "1\u00a0234 части")
        i18n._tables["en"] = {"нет данных": "no data", "# часть|# части|# частей": "# part|# parts",
                              "в хранилище {0} из {1} частей": "{0} of {1} parts vaulted"}
        try:
            self.assertEqual(i18n.tr("нет данных", lang="en"), "no data")
            self.assertEqual(i18n.tr("  нет данных ", lang="en"), "  no data ", "the spaces around a text are the code's business")
            self.assertEqual(i18n.tr("в хранилище {0} из {1} частей", 2, 4, lang="en"), "2 of 4 parts vaulted")
            self.assertEqual([i18n.tn("# часть|# части|# частей", n, lang="en") for n in (1, 2, 1000)], ["1 part", "2 parts", "1,000 parts"])
            self.assertEqual(i18n.tr("такого текста нет", lang="en"), "такого текста нет")
            self.assertEqual(i18n.tn("# снимок|# снимка|# снимков", 3, lang="en"), "3 снимка", "an untranslated text keeps the Russian rule")
        finally:
            i18n.forget_tables()

    def test_page_script_cannot_break_out_of_the_script_tag(self):
        i18n._tables["en"] = {"x": "</script><b>"}
        try:
            script = i18n.page_script("en")
        finally:
            i18n.forget_tables()
        self.assertNotIn("</script>", script)
        self.assertTrue(script.startswith("window.I18N = {"))
        page = json.loads(script[len("window.I18N = "):].rstrip(";\n"))
        self.assertEqual((page["lang"], page["locale"], page["plural"], len(page["languages"])), ("en", "en-US", ["one", "other"], 6))

    def test_html_texts_are_escaped(self):
        i18n._tables["en"] = {"Поиск": 'Search "<b>"'}
        try:
            html = i18n.render_html('<html lang="{{lang}}"><input placeholder="{{t:Поиск}}"><p>{{t:Нет перевода}}</p>', "en")
        finally:
            i18n.forget_tables()
        self.assertEqual(html, '<html lang="en"><input placeholder="Search &quot;&lt;b&gt;&quot;"><p>Нет перевода</p>')

    def test_every_language_has_every_text(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import i18n_keys
        keys = i18n_keys.collect()
        self.assertGreater(len(keys), 400)
        for lang in i18n.LANGS:
            if lang == i18n.SOURCE:
                continue
            missing, wrong, _extra = i18n_keys.problems(lang, keys)
            self.assertEqual((lang, missing[:5], wrong[:5]), (lang, [], []))


class NamesInOtherLanguages(unittest.TestCase):
    """Item names as warframe.market gives them in each language (checked against the live site, 2026-11)."""

    NAMES = {
        "de": ("Mirage Prime: Set", "Mirage Prime: Systeme Blaupause", "Mirage Prime Blaupause", "Silva & Ägis Prime: Schutz"),
        "fr": ("Mirage Prime - Set", "Mirage Prime - Systèmes (Schéma)", "Mirage Prime (Schéma)", "Silva & Aegis Prime - Quillon"),
        "pl": ("Mirage Prime: Zestaw", "Mirage Prime: Systemy - Schemat", "Mirage Prime - Schemat", "Silva I Aegis Prime: Garda"),
        "zh": ("Mirage Prime 一套", "Mirage Prime 系统 蓝图", "Mirage Prime 蓝图", "席瓦 & 神盾 Prime 护手"),
        "en": ("Mirage Prime Set", "Mirage Prime Systems Blueprint", "Mirage Prime Blueprint", "Silva & Aegis Prime Guard"),
        "ru": ("Мираж Прайм: Комплект", "Мираж Прайм: Система (Чертеж)", "Мираж Прайм (Чертеж)", "Сильва и Эгида Прайм: Гарда"),
    }

    def test_titles_and_labels(self):
        expect = {"de": ("Systeme Blaupause", "Blaupause"), "fr": ("Systèmes (Schéma)", "Schéma"), "pl": ("Systemy - Schemat", "Schemat"),
                  "zh": ("系统 蓝图", "蓝图"), "en": ("Systems Blueprint", "Blueprint"), "ru": ("Система (чертёж)", "Чертёж")}
        for lang, (set_name, systems, blueprint, _guard) in self.NAMES.items():
            title = catalog.set_title(set_name)
            self.assertEqual(title, "Мираж Прайм" if lang == "ru" else "Mirage Prime", lang)
            self.assertEqual((catalog.part_label(systems, title, lang), catalog.part_label(blueprint, title, lang)), expect[lang], lang)
        self.assertEqual(catalog.set_title("Reset Prime Set"), "Reset Prime", "only a separate word is the suffix")

    def test_captions_match_in_the_language_of_the_game(self):
        for lang, (set_name, systems, blueprint, guard) in self.NAMES.items():
            title = catalog.set_title(set_name)
            cat = {"sets": {"mirage_prime_set": {
                "slug": "mirage_prime_set", "name": "Мираж Прайм: Комплект", "en": "Mirage Prime Set", "title": "Мираж Прайм",
                "title_en": "Mirage Prime", "title_game": title, "category": "warframe", "parts": [
                    {"slug": "sys", "name": "Мираж Прайм: Система (Чертеж)", "en": "Mirage Prime Systems Blueprint", "game": systems,
                     "blueprint": True},
                    {"slug": "bp", "name": "Мираж Прайм (Чертеж)", "en": "Mirage Prime Blueprint", "game": blueprint, "blueprint": True},
                    {"slug": "guard", "name": "Сильва и Эгида Прайм: Гарда", "en": "Silva & Aegis Prime Guard", "game": guard,
                     "blueprint": False}]}}}
            m = Matcher(cat)
            self.assertEqual((m.match(systems).slug, m.match(blueprint).slug, m.match(guard).slug), ("sys", "bp", "guard"), lang)
            self.assertEqual(m.match(systems.upper()).slug, "sys", lang)
            self.assertTrue(split_blueprint(blueprint)[1], lang)
            self.assertEqual(m.match_set(title).slug, "mirage_prime_set", lang)
        self.assertEqual(Matcher(cat).match("Silva and Aegis Prime Guard").slug, "guard", "& and the word for it are the same")
        wrong = Matcher(cat).match("Mirage Prime系统蓝图")          # the catalog here has no Chinese names
        self.assertFalse(wrong.status == "exact" or (wrong.ok and wrong.confident),
                         "without the names of the game's language a caption is at most a guess to be checked")

    def test_chinese_without_spaces_and_accents(self):
        self.assertEqual(normalize("Mirage Prime系统蓝图"), normalize("Mirage Prime 系统 蓝图"))
        self.assertEqual(normalize("Systèmes (SCHÉMA)"), "systemes schema")
        self.assertEqual(normalize("Silva & Ägis"), "silva и agis")
        self.assertEqual(normalize("Сильва и Эгида Прайм: Чертёж"), "сильва и эгида прайм чертеж", "Russian keys are as they always were")


# --------------------------------------------------------------------------- the request and the answer
class Request(Base):
    def test_the_russian_request_is_the_checked_one(self):
        task = recognize.task("ru", "ru")
        self.assertIn("ЕСЛИ ЭТО ИНВЕНТАРЬ", task.prompt_files)
        self.assertEqual(task.prompt_files.split("screen —")[1], task.prompt_attached.split("screen —")[1], "one text, two openings")
        self.assertIn("  a.png\n  b.png", task.files_text([Path("a.png"), Path("b.png")]))
        self.assertNotIn("Read", task.prompt_attached + task.system_attached)

    def test_other_clients_get_their_language_and_word_for_blueprint(self):
        for lang, word in (("en", "Blueprint"), ("de", "Blaupause"), ("fr", "Schéma"), ("pl", "Schemat"), ("zh", "蓝图")):
            task = recognize.task(lang, "pl")
            self.assertIn(f'"{word}"', task.prompt_attached, lang)
            self.assertIn("Write the notes field in Polish", task.prompt_attached, lang)
            self.assertNotIn("{", task.prompt_attached, lang)
            task.files_text([self.tile])                      # the only placeholder is the list of files
        self.assertIn("Write the notes field in German", recognize.task("ru", "de").prompt_attached)

    def test_schema_is_strict(self):
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(sorted(node["required"]), sorted(node["properties"]))
                for value in node.values():
                    walk(value)
        walk(recognize.SCHEMA)

    def test_an_answer_is_never_taken_on_trust(self):
        got = recognize.clean_answer({"screen": "desktop", "notes": None, "extra": 1, "items": [
            {"name": "  Васто Прайм: Ствол ", "rank": "30", "count": "3", "count_visible": "yes", "cut_top": 1,
             "blueprint_word": True, "mastered_label": "true", "owned_label": False, "junk": {}, "row": 2, "col": "3"},
            {"name": ""}, "not an item", {"name": "Мираж Прайм", "rank": True, "count": None, "row": 0, "col": True}]})
        self.assertEqual(got, {"screen": "other", "notes": "", "items": [
            {"name": "Васто Прайм: Ствол", "rank": None, "count": 3, "count_visible": False, "cut_top": False,
             "blueprint_word": True, "mastered_label": None, "owned_label": False, "row": 2, "col": None},
            {"name": "Мираж Прайм", "rank": None, "count": 1, "count_visible": False, "cut_top": False,
             "blueprint_word": False, "mastered_label": None, "owned_label": None, "row": None, "col": None}]})
        for junk in (["a list"], {"answer": 42}, "text", None):
            with self.assertRaises(ProviderError):
                recognize.clean_answer(junk)


# --------------------------------------------------------------------------- the web APIs
@unittest.skipUnless(vault.available(), "the key store needs Windows")
class WebApis(Base):
    def setUp(self):
        super().setUp()
        self.api = FakeApi()
        for pid in ("openai_api", "deepseek_api", "gemini_api", "anthropic_api"):
            vault.put(pid, KEY)
        settings.save({"base_urls": {"openai_api": self.api.url + "/v1", "deepseek_api": self.api.url,
                                     "gemini_api": self.api.url + "/v1beta", "anthropic_api": self.api.url}})

    def tearDown(self):
        self.api.close()
        super().tearDown()

    def read(self, pid):
        return providers.get(pid).read(self.work, [self.tile], self.task)

    def test_openai_request_and_answer(self):
        got = self.read("openai_api")
        self.assertEqual(recognize.clean_answer(got["data"])["items"][0]["count"], 2)
        req = self.api.requests[-1]
        self.assertEqual((req["method"], req["path"], req["headers"]["Authorization"]), ("POST", "/v1/responses", "Bearer " + KEY))
        body = req["body"]
        self.assertEqual((body["model"], body["store"], body["text"]["format"]["type"], body["text"]["format"]["strict"]),
                         ("gpt-6.2-astra", False, "json_schema", True))
        self.assertEqual(body["text"]["format"]["schema"], recognize.SCHEMA)
        parts = body["input"][0]["content"]
        self.assertEqual([p["type"] for p in parts], ["input_text", "input_image"])
        self.assertTrue(parts[1]["image_url"].startswith("data:image/png;base64,iVBOR"))
        self.assertNotIn(KEY, json.dumps(body))

    def test_openai_model_without_reasoning_is_asked_again(self):
        self.api.plan = [(400, {"error": {"message": "Unsupported parameter: 'reasoning.effort' is not supported with this model."}})]
        self.read("openai_api")
        first, second = self.api.requests[-2]["body"], self.api.requests[-1]["body"]
        self.assertIn("reasoning", first)
        self.assertNotIn("reasoning", second)

    def test_openai_errors_tell_the_user_what_to_do(self):
        cases = [((401, {"error": {"message": "Incorrect API key provided"}}), "bad_key"),
                 ((403, {"error": {"message": "Country, region, or territory not supported"}}), "network"),
                 ((429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details"}}), "quota"),
                 ((404, {"error": {"message": "The model does not exist"}}), "model"),
                 ((400, {"error": {"message": "Invalid image"}}), "error")]
        for answer, code in cases:
            self.api.plan = [answer] * 4
            with self.assertRaises(ProviderError) as ctx:
                self.read("openai_api")
            self.assertEqual(ctx.exception.code, code, answer)
            self.assertNotIn(KEY, str(ctx.exception))
        self.api.plan = [(200, {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "refusal", "refusal": "I can't help with that"}]}]})]
        with self.assertRaises(ProviderError) as ctx:
            self.read("openai_api")
        self.assertEqual(ctx.exception.code, "refused")

    def test_a_key_quoted_back_by_the_service_is_not_shown(self):
        self.api.plan = [(401, {"error": {"message": f"Incorrect API key provided: {KEY}. Find your key at the dashboard."}})]
        with self.assertRaises(ProviderError) as ctx:
            self.read("openai_api")
        self.assertNotIn(KEY, str(ctx.exception))
        self.assertIn("***", str(ctx.exception))
        self.api.plan = [(400, {"error": {"code": 400, "message": f"API key not valid: {KEY}"}})] * 2
        with self.assertRaises(ProviderError) as ctx:
            self.read("gemini_api")
        self.assertNotIn(KEY, str(ctx.exception))

    def test_openai_check_lists_the_models_that_read(self):
        got = providers.get("openai_api").check()
        self.assertEqual((got["ok"], got["models"]), (True, ["gpt-6.2-astra"]))
        self.api.plan = [(401, {"error": {"message": "bad key"}})]
        self.assertFalse(providers.get("openai_api").check()["ok"])

    def test_deepseek_gets_the_schema_in_words_and_a_blank_answer_is_asked_again(self):
        self.api.plan = [(200, {"choices": [{"finish_reason": "stop", "message": {"content": "   "}}]})]
        got = self.read("deepseek_api")
        self.assertEqual(got["data"]["items"][0]["name"], "Васто Прайм: Ствол")
        req = self.api.requests[-1]
        self.assertEqual((req["path"], req["headers"]["Authorization"]), ("/chat/completions", "Bearer " + KEY))
        body = req["body"]
        self.assertEqual((body["model"], body["response_format"]), ("deepseek-flash", {"type": "json_object"}))
        self.assertIn("JSON", body["messages"][0]["content"])
        self.assertIn('"cut_top"', body["messages"][0]["content"])
        self.assertEqual([p["type"] for p in body["messages"][1]["content"]], ["text", "image_url"])
        self.assertEqual(len(self.api.requests), 2)

    def test_gemini_request_and_answer(self):
        got = self.read("gemini_api")
        self.assertEqual(got["data"]["screen"], "inventory")
        req = self.api.requests[-1]
        head = {k.lower(): v for k, v in req["headers"].items()}
        self.assertEqual((req["path"], head["x-goog-api-key"], head["api-revision"]), ("/v1beta/interactions", KEY, "2026-05-20"))
        body = req["body"]
        self.assertEqual((body["model"], body["response_format"]["mime_type"], body["response_format"]["schema"], body["store"]),
                         ("gemini-4-hydrogen", "application/json", recognize.SCHEMA, False))
        self.assertEqual([(p["type"], p.get("mime_type")) for p in body["input"]], [("text", None), ("image", "image/png")])
        self.assertEqual(providers.get("gemini_api").check()["models"], ["gemini-4-hydrogen"])

    @unittest.skipUnless(anthropic_sdk(), "the anthropic library is not installed")
    def test_anthropic_request_and_answer(self):
        got = self.read("anthropic_api")
        self.assertEqual(got["data"]["items"][0]["count"], 2)
        req = self.api.requests[-1]
        head = {k.lower(): v for k, v in req["headers"].items()}
        self.assertEqual(req["path"].split("?")[0], "/v1/messages")
        # the key travels in a header (which one depends on the version of the library) and nowhere else
        self.assertIn(KEY, head.get("x-api-key", "") + head.get("authorization", ""))
        self.assertNotIn(KEY, json.dumps(req["body"]))
        self.assertIn("server-side-fallback-2026-07-01", head.get("anthropic-beta", ""))
        body = req["body"]
        self.assertEqual((body["model"], body["fallbacks"], body["output_config"]["effort"], body["output_config"]["format"]["type"]),
                         ("claude-opus-5-5", "default", "low", "json_schema"))
        self.assertEqual(body["output_config"]["format"]["schema"], recognize.SCHEMA)
        self.assertEqual([b["type"] for b in body["messages"][0]["content"]], ["image", "text"])
        self.assertNotIn("thinking", body)
        self.assertNotIn("temperature", body)

    @unittest.skipUnless(anthropic_sdk(), "the anthropic library is not installed")
    def test_anthropic_a_gateway_that_rejects_the_extras_still_gets_a_plain_request(self):
        bad = (400, {"type": "error", "error": {"type": "invalid_request_error", "message": "fallbacks: Extra inputs are not permitted"}})
        self.api.plan = [bad]
        self.read("anthropic_api")
        self.assertNotIn("fallbacks", self.api.requests[-1]["body"])
        settings.save({"models": {"anthropic_api": "claude-haiku-5-5"}})
        self.read("anthropic_api")
        self.assertNotIn("fallbacks", self.api.requests[-1]["body"], "no fallback for a model that has none")
        self.api.plan = [(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})]
        with self.assertRaises(ProviderError) as ctx:
            self.read("anthropic_api")
        self.assertEqual(ctx.exception.code, "bad_key")

    def test_a_whole_reading_through_an_api(self):
        inbox = shots.config.SCREENSHOT_DIR
        if inbox.exists():
            import shutil
            shutil.rmtree(inbox)
        inbox.mkdir(parents=True)
        for f in (inventory.config.INVENTORY_FILE, mastery.MASTERY_FILE):
            if f.exists():
                f.unlink()
        (inbox / "one.png").write_bytes(test_core.Recognition.tiny_png())
        settings.save({"provider": "gemini_api"})
        job = recognize.Job(shots.originals(), make_catalog())
        job.run()
        snap = job.snapshot()
        self.assertEqual((snap["state"], snap["reports"]["replace"]["distinct_parts"]), ("review", 1), snap)
        vault.put("gemini_api", "")
        job = recognize.Job(shots.originals(), make_catalog())
        job.run()
        self.assertEqual((job.snapshot()["state"], job.snapshot()["error_code"]), ("error", "no_key"))
        recognize.forget_pending()


class PendingReading(Base):
    """A reading that waits for the user's decision when the language of the settings changes."""

    def setUp(self):
        super().setUp()
        os.environ["PRIMESETS_CLAUDE_CMD"] = json.dumps(FAKE_CLAUDE)
        os.environ["FAKE_RECOGNIZE_MODE"] = "ok"
        self.data = Path(_TMP.name) / "fake_pending.json"
        self.data.write_text(json.dumps({"*": {"screen": "inventory", "notes": "", "items": [
            dict(ANSWER["items"][0], name="Васто Прайм: Ствол"),
            dict(ANSWER["items"][0], name="Чертёж: Мираж Прайм: Система", blueprint_word=True),
            dict(ANSWER["items"][0], name="Зюзя Прайм: Хвост")]}}, ensure_ascii=False), encoding="utf-8")
        os.environ["FAKE_RECOGNIZE_DATA"] = str(self.data)
        providers.get("claude_cli").forget_status()
        inbox = shots.config.SCREENSHOT_DIR
        if inbox.exists():
            import shutil
            shutil.rmtree(inbox)
        inbox.mkdir(parents=True)
        (inbox / "one.png").write_bytes(test_core.Recognition.tiny_png())
        for f in (inventory.config.INVENTORY_FILE, mastery.MASTERY_FILE):
            if f.exists():
                f.unlink()

    def tearDown(self):
        for key in ("PRIMESETS_CLAUDE_CMD", "FAKE_RECOGNIZE_MODE", "FAKE_RECOGNIZE_DATA"):
            os.environ.pop(key, None)
        recognize.forget_pending()
        super().tearDown()

    @staticmethod
    def english_only(cat):
        """The same catalog as a player with an English interface and an English game would have."""
        out = json.loads(json.dumps(cat))
        for st in out["sets"].values():
            st["name"], st["title"], st["title_game"] = st["en"], st["title_en"], st["title_en"]
            for p in st["parts"]:
                p["name"] = p["game"] = p["en"]
        return out

    def test_a_corrected_game_language_matches_the_captions_again(self):
        russian = make_catalog()
        job = recognize.Job(shots.originals(), self.english_only(russian))     # the game language was set wrong
        job.run()
        rep = job.snapshot()["reports"]["merge"]
        self.assertEqual((job.state, len(rep["matched"]), len(rep["review"])), ("review", 0, 3))
        job.reword(russian)                                                    # ...and is corrected in the settings
        rep = job.snapshot()["reports"]["merge"]
        self.assertEqual((sorted(m["item"] for m in rep["matched"]), [r["name"] for r in rep["review"]]),
                         (["Васто Прайм: Ствол", "Мираж Прайм: Система (Чертеж)"], ["Зюзя Прайм: Хвост"]))
        self.assertIs(job.catalog, russian)

    def test_a_changed_interface_language_keeps_a_good_reading(self):
        russian = make_catalog()
        job = recognize.Job(shots.originals(), russian)
        job.run()
        self.assertEqual(len(job.snapshot()["reports"]["merge"]["matched"]), 2)
        i18n._tables["en"] = {"нет такого названия в каталоге": "no such name in the catalog"}
        try:
            i18n.set_language("en")
            job.reword(self.english_only(russian))        # the interface went English, the game did not
            rep = job.snapshot()["reports"]["merge"]
        finally:
            i18n.forget_tables()
        self.assertEqual((len(rep["matched"]), [r["note"] for r in rep["review"]]), (2, ["no such name in the catalog"]))
        self.assertIs(job.catalog, russian, "the reading stays with the names it was read with")


# --------------------------------------------------------------------------- Codex
class Codex(Base):
    def setUp(self):
        super().setUp()
        os.environ["PRIMESETS_CODEX_CMD"] = json.dumps(FAKE_CODEX)
        os.environ["FAKE_CODEX_MODE"] = "ok"
        os.environ["OPENAI_API_KEY"] = "must-not-reach-the-child"
        self.data = Path(_TMP.name) / "fake_codex_data.json"
        self.data.write_text(json.dumps({"*": ANSWER}, ensure_ascii=False), encoding="utf-8")
        os.environ["FAKE_RECOGNIZE_DATA"] = str(self.data)
        self.codex = providers.get("codex_cli")
        self.codex.forget_status()

    def tearDown(self):
        for key in ("PRIMESETS_CODEX_CMD", "FAKE_CODEX_MODE", "OPENAI_API_KEY", "FAKE_RECOGNIZE_DATA"):
            os.environ.pop(key, None)
        self.codex.forget_status()
        super().tearDown()

    def test_status_and_reading(self):
        self.assertEqual(codex_cli.find(), FAKE_CODEX)
        st = self.codex.status(force=True)
        self.assertEqual((st["available"], st["logged_in"], st["ready"], st["method"]), (True, True, True, "chatgpt"))
        got = self.codex.read(self.work, [self.tile], self.task)
        self.assertEqual(got["data"]["items"][0]["name"], "Васто Прайм: Ствол")
        self.assertFalse(any(k.startswith("OPENAI") for k in self.codex.env()), "the ChatGPT sign-in is used, never a key")

    def test_not_signed_in(self):
        os.environ["FAKE_CODEX_MODE"] = "not_logged_in"
        st = self.codex.status(force=True)
        self.assertEqual((st["ready"], st["reason"]), (False, "login"))
        with self.assertRaises(ProviderError) as ctx:
            self.codex.read(self.work, [self.tile], self.task)
        self.assertEqual(ctx.exception.code, "login")

    def test_a_blocked_network_points_at_the_proxy(self):
        os.environ["FAKE_CODEX_MODE"] = "network"
        with self.assertRaises(ProviderError) as ctx:
            self.codex.read(self.work, [self.tile], self.task)
        self.assertEqual(ctx.exception.code, "network")

    @unittest.skipUnless(vault.available(), "the key store needs Windows")
    def test_the_proxy_reaches_only_the_program_it_was_switched_on_for(self):
        vault.put(vault.PROXY, "http://proxy.example:3128")
        settings.save({"use_proxy": {"codex_cli": True}})
        self.assertEqual(self.codex.env().get("HTTPS_PROXY"), "http://proxy.example:3128")
        os.environ["PRIMESETS_CLAUDE_CMD"] = json.dumps(FAKE_CLAUDE)
        try:
            self.assertNotEqual(providers.get("claude_cli").env().get("HTTPS_PROXY"), "http://proxy.example:3128")
        finally:
            del os.environ["PRIMESETS_CLAUDE_CMD"]


if __name__ == "__main__":
    unittest.main()
