"""A stand-in for the Claude Code CLI, used by the tests and for trying the interface offline.

It understands just what primesets.recognize sends:
    fake_claude.py auth status
    fake_claude.py -p --output-format json ... (prompt on stdin)

FAKE_RECOGNIZE_MODE = ok | not_logged_in | garbage | slow
FAKE_RECOGNIZE_DATA = path to a JSON file {"<tile name prefix>": {...structured output...}, "*": {...}}
"""
import json
import os
import re
import sys
import time

mode = os.environ.get("FAKE_RECOGNIZE_MODE", "ok")
args = sys.argv[1:]

if args[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": mode != "not_logged_in", "authMethod": "claude.ai" if mode != "not_logged_in" else "none"}))
    sys.exit(0)

if "-p" not in args:
    print("fake claude: unsupported call", args, file=sys.stderr)
    sys.exit(2)

# the real CLI must be called in a way that cannot run commands or leave the folder
for needed in ("--restricted", "--safe-mode", "--no-session-persistence", "--json-schema"):
    if needed not in args:
        print(f"fake claude: missing {needed}", file=sys.stderr)
        sys.exit(3)
if args[args.index("--tools") + 1] != "Read":
    print("fake claude: tools must be Read only", file=sys.stderr)
    sys.exit(3)
if any(k.upper().startswith(("ANTHROPIC", "CLAUDE_CODE")) for k in os.environ):
    print("fake claude: auth-related environment leaked into the child", file=sys.stderr)
    sys.exit(3)

prompt = sys.stdin.buffer.read().decode("utf-8")
files = re.findall(r"^\s+(\S+\.(?:png|jpg|jpeg|webp|bmp))\s*$", prompt, flags=re.M | re.I)
for name in files:
    if not os.path.isfile(name):
        print(f"fake claude: {name} is not in the working folder", file=sys.stderr)
        sys.exit(4)

if mode == "not_logged_in":
    print(json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}))
    sys.exit(0)
if mode == "garbage":
    print("this is not json")
    sys.exit(0)
time.sleep(3.0 if mode == "slow" else 0.2)

data = {}
path = os.environ.get("FAKE_RECOGNIZE_DATA")
if path:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
answer = None
for prefix, value in data.items():
    if prefix != "*" and files and files[0].startswith(prefix):
        answer = value
        break
if answer is None:
    answer = data.get("*") or {"screen": "inventory", "items": [], "notes": ""}

# the real CLI writes UTF-8 whatever the console code page is
sys.stdout.buffer.write(json.dumps({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 200,
                                    "result": "готово", "structured_output": answer}, ensure_ascii=False).encode("utf-8"))
sys.stdout.buffer.write(b"\n")
