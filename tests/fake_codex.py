"""A stand-in for the Codex CLI, used by the tests.

It understands just what primesets.providers.codex_cli sends:
    fake_codex.py login status
    fake_codex.py exec --image F ... --output-schema S --output-last-message O ... -   (request on stdin)

FAKE_CODEX_MODE = ok | not_logged_in | network
FAKE_RECOGNIZE_DATA = path to a JSON file {"<tile name prefix>": {...answer...}, "*": {...}}
"""
import json
import os
import sys

mode = os.environ.get("FAKE_CODEX_MODE", "ok")
args = sys.argv[1:]

if args[:2] == ["login", "status"]:
    if mode == "not_logged_in":
        print("Not logged in", file=sys.stderr)
        sys.exit(1)
    print("Logged in using ChatGPT", file=sys.stderr)
    sys.exit(0)

if not args or args[0] != "exec":
    print("fake codex: unsupported call", args, file=sys.stderr)
    sys.exit(2)


def value(flag):
    return args[args.index(flag) + 1]


# the real program must be called so that it can change nothing and remembers nothing
for needed in ("--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--output-schema", "--output-last-message"):
    if needed not in args:
        print(f"fake codex: missing {needed}", file=sys.stderr)
        sys.exit(3)
if value("--sandbox") != "read-only":
    print("fake codex: the sandbox must be read-only", file=sys.stderr)
    sys.exit(3)
if args[-1] != "-":
    print("fake codex: the request must come through stdin", file=sys.stderr)
    sys.exit(3)
if any(k.upper().startswith("OPENAI") for k in os.environ):
    print("fake codex: an API key leaked into the child", file=sys.stderr)
    sys.exit(3)

images = [args[i + 1] for i, a in enumerate(args) if a == "--image"]
for name in images:
    if not os.path.isfile(name):
        print(f"fake codex: {name} does not exist", file=sys.stderr)
        sys.exit(4)
if not images:
    print("fake codex: no images", file=sys.stderr)
    sys.exit(4)
with open(value("--output-schema"), encoding="utf-8") as fh:
    schema = json.load(fh)
if schema.get("additionalProperties") is not False:
    print("fake codex: the schema must be strict", file=sys.stderr)
    sys.exit(4)
prompt = sys.stdin.buffer.read().decode("utf-8")
if "Warframe" not in prompt:
    print("fake codex: no request on stdin", file=sys.stderr)
    sys.exit(4)

if mode == "not_logged_in":
    print("ERROR: Not logged in. Run `codex login`.", file=sys.stderr)
    sys.exit(1)
if mode == "network":
    print("ERROR: Failed to refresh token: 403 Forbidden\nReconnecting... 5/5", file=sys.stderr)
    sys.exit(1)

data = {}
path = os.environ.get("FAKE_RECOGNIZE_DATA")
if path:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
first = os.path.basename(images[0])
answer = None
for prefix, item in data.items():
    if prefix != "*" and first.startswith(prefix):
        answer = item
        break
if answer is None:
    answer = data.get("*") or {"screen": "inventory", "items": [], "notes": ""}
with open(value("--output-last-message"), "w", encoding="utf-8") as fh:
    json.dump(answer, fh, ensure_ascii=False)
print("done")
