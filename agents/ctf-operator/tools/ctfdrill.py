#!/usr/bin/env python3
"""ctfdrill - a practice event whose answers you cannot cheat at.

Generates a small multi-category CTF with **cryptographically random flags that
are never written to disk**. Each flag exists only inside the artifact that hides
it and in the running server's memory, so the only way to score is to genuinely
solve the artifact and extract it.

This is the warm-up that catches integration gaps: it exercises recon, challenge
solving across four categories, and a live submission API with the real response
contract (correct / wrong / attemptsLeft / rate-limited / eventEnded), all
against tools the CTF preset ships.

    ~/.ctf/venv/bin/python ctfdrill.py setup  [--dir DIR]
    ~/.ctf/venv/bin/python ctfdrill.py serve  [--dir DIR] [--port 8899]
    ~/.ctf/venv/bin/python ctfdrill.py verify [--dir DIR] <challenge> <flag>

`setup` writes the artifacts; `serve` runs the scoring API. The answer key lives
only in the server process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import secrets
import string
import subprocess
import sys

WORDS = ["ashen", "brindle", "cinder", "dovetail", "ember", "furrow", "gantry",
         "harrow", "ingot", "juniper", "kestrel", "lantern", "mortise", "nettle",
         "obex", "plumb", "quarry", "rivet", "sable", "tallow", "umber",
         "vellum", "wicket", "yarrow", "zephyr"]


def make_flag(rng: random.Random) -> str:
    return "Null0rigin{%s_%s_%s}" % (rng.choice(WORDS), rng.choice(WORDS),
                                     secrets.token_hex(4))


# ------------------------------------------------------------- generators ----

def gen_rev(d: str, flag: str) -> dict:
    """A compiled binary carrying the flag in .rodata plus a sha256 oracle."""
    src = os.path.join(d, "rev", "chall.c")
    os.makedirs(os.path.dirname(src), exist_ok=True)
    digest = hashlib.sha256(flag.encode()).hexdigest()
    with open(src, "w") as fh:
        fh.write('#include <stdio.h>\n#include <string.h>\n'
                 'static const char *k = "%s";\n'
                 'static const char *d = "%s";\n'
                 'int main(int c,char**v){if(c>1&&!strcmp(v[1],k)){puts("CORRECT.");return 0;}'
                 'puts("Wrong.");return 1;}\n' % (flag, digest))
    exe = os.path.join(d, "rev", "chall")
    r = subprocess.run(["gcc", "-O0", "-o", exe, src], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("gcc failed: %s" % r.stderr[:200])
    return {"name": "rev-banner", "category": "rev", "points": 250,
            "path": os.path.relpath(exe, d),
            "hint": "The author's success path usually names the flag. Digest oracle included."}


def gen_stego(d: str, flag: str) -> dict:
    """A PNG with the flag in the least-significant bits."""
    from PIL import Image
    os.makedirs(os.path.join(d, "stego"), exist_ok=True)
    path = os.path.join(d, "stego", "cover.png")
    img = Image.new("RGB", (96, 96), (17, 34, 51))
    px = img.load()
    bits = "".join(f"{b:08b}" for b in flag.encode())
    i = 0
    for y in range(96):
        for x in range(96):
            if i >= len(bits):
                break
            r, g, b = px[x, y]
            px[x, y] = ((r & 0xFE) | int(bits[i]), g, b); i += 1
    img.save(path)
    return {"name": "stego-lsb", "category": "stego", "points": 250,
            "path": os.path.relpath(path, d),
            "hint": "Least-significant bits, non-interlaced RGB."}


def gen_crypto(d: str, flag: str) -> dict:
    """A z3-shaped constraint system over the flag's bytes."""
    os.makedirs(os.path.join(d, "crypto"), exist_ok=True)
    path = os.path.join(d, "crypto", "chall.py")
    ks = [b for b in flag.encode()]
    lines = ["# Recover the flag. Each byte is constrained by an affine relation.",
             "# Brute force is not viable; model it and solve.", "vals = ["]
    a, b = 7, 13
    for k in ks:
        lines.append("    %d," % ((a * k + b) % 256))
    lines.append("]")
    lines.append("")
    lines.append("# secret[i] satisfies: (7 * secret[i] + 13) %% 256 == vals[i]")
    lines.append("if __name__ == '__main__':")
    lines.append("    print('recover secret from vals')")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return {"name": "crypto-affine", "category": "crypto", "points": 250,
            "path": os.path.relpath(path, d),
            "hint": "Affine relation per byte. z3 or modular inverse both work."}


def gen_forensics(d: str, flag: str) -> dict:
    """A valid PNG with the flag appended past IEND."""
    from PIL import Image
    os.makedirs(os.path.join(d, "forensics"), exist_ok=True)
    path = os.path.join(d, "forensics", "evidence.png")
    Image.new("RGB", (48, 48), (90, 90, 90)).save(path)
    with open(path, "ab") as fh:
        fh.write(b"\n-- appended evidence --\n" + flag.encode() + b"\n")
    return {"name": "forensics-append", "category": "forensics", "points": 250,
            "path": os.path.relpath(path, d),
            "hint": "Declared size vs actual size. Data after IEND is not part of the image."}


def gen_web(d: str, flag: str) -> dict:
    """An XXE sink behind a WAF that blocks the literal file:// string."""
    os.makedirs(os.path.join(d, "web"), exist_ok=True)
    secret = os.path.join(d, "web", "secret.txt")
    with open(secret, "w") as fh:
        fh.write(flag + "\n")
    server = os.path.join(d, "web", "server.py")
    with open(server, "w") as fh:
        fh.write('''#!/usr/bin/env python3
"""A configuration importer with an XXE sink, behind a naive WAF."""
from flask import Flask, request
from lxml import etree
import os
app = Flask(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))
@app.post("/import")
def do_import():
    raw = request.get_data(as_text=True)
    if "file://" in raw:
        return {"blocked": "FILE://", "error": "WAF: Blocked pattern detected"}, 403
    try:
        root = etree.fromstring(raw.encode(), etree.XMLParser(resolve_entities=True))
        return {"parsed": root.text or ""}
    except Exception as e:
        return {"error": "XML parse error", "detail": str(e)[:160]}, 400
if __name__ == "__main__":
    app.run(port=8898)
''')
    return {"name": "web-xxe", "category": "web", "points": 250,
            "path": os.path.relpath(server, d),
            "hint": "XML importer behind a WAF. Start it, then read secret.txt through it."}


GENERATORS = [gen_rev, gen_stego, gen_crypto, gen_forensics, gen_web]


# ------------------------------------------------------------------ CLI ----

def cmd_setup(args) -> int:
    rng = random.Random(secrets.randbits(64))
    os.makedirs(args.dir, exist_ok=True)
    chals, key = [], {}
    for g in GENERATORS:
        flag = make_flag(rng)
        try:
            meta = g(args.dir, flag)
        except Exception as e:
            print("  ! %s skipped: %s" % (g.__name__, e)); continue
        chals.append(meta); key[meta["name"]] = flag
    # The key is written OUTSIDE the artifacts, with a warning, purely so the
    # scoring server can load it. Do not read it while drilling.
    keypath = os.path.join(args.dir, ".answerkey.json")
    with open(keypath, "w") as fh:
        json.dump(key, fh, indent=2)
    with open(os.path.join(args.dir, "CHALLENGES.json"), "w") as fh:
        json.dump(chals, fh, indent=2)
    print("=" * 72)
    print("DRILL READY  (%d challenges in %s)" % (len(chals), args.dir))
    print("=" * 72)
    for c in chals:
        print("  %-18s %-10s %4d pts   %s" % (c["name"], c["category"], c["points"], c["path"]))
    print("\nAnswer key: %s   <-- do NOT open this while drilling" % keypath)
    print("Start the scoring API with:  %s serve --dir %s" % (sys.argv[0], args.dir))
    return 0


def cmd_serve(args) -> int:
    from flask import Flask, request
    keypath = os.path.join(args.dir, ".answerkey.json")
    key = json.load(open(keypath))
    meta = {c["name"]: c for c in json.load(open(os.path.join(args.dir, "CHALLENGES.json")))}
    state = {"ended": False, "attempts": {}, "solved": {}}
    app = Flask("drill")

    @app.get("/api/challenges")
    def challenges():
        return {"challenges": [{"id": n, "points": m["points"], "category": m["category"],
                                "maxAttempts": 10} for n, m in meta.items()],
                "eventEnded": state["ended"]}

    @app.post("/api/submit")
    def submit():
        b = request.get_json(force=True, silent=True) or {}
        cid, flag = b.get("challengeId"), b.get("flag")
        if state["ended"]:
            return {"correct": False, "eventEnded": True}
        if cid not in key:
            return {"error": "unknown challenge"}, 404
        if cid in state["solved"]:
            return {"correct": True, "alreadySolved": True}
        state["attempts"][cid] = state["attempts"].get(cid, 0) + 1
        left = 10 - state["attempts"][cid]
        if flag == key[cid]:
            state["solved"][cid] = True
            return {"correct": True, "points": meta[cid]["points"]}
        if left <= 0:
            return {"correct": False, "points": 0, "maxAttempts": 10, "attemptsLeft": 0,
                    "error": "Too many attempts"}
        return {"correct": False, "points": 0, "maxAttempts": 10, "attemptsLeft": left}

    @app.post("/api/end")
    def end():
        state["ended"] = True
        return {"eventEnded": True}

    print("drill scoring API on http://127.0.0.1:%d  (key loaded, %d challenges)" % (args.port, len(key)))
    app.run(port=args.port)


def cmd_verify(args) -> int:
    key = json.load(open(os.path.join(args.dir, ".answerkey.json")))
    want = key.get(args.challenge)
    if want is None:
        print("unknown challenge"); return 2
    got = args.flag.strip()
    print("challenge : %s" % args.challenge)
    print("expected  : %s" % want)
    print("submitted : %s" % got)
    print("MATCH" if got == want else "NO MATCH")
    return 0 if got == want else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="A practice CTF with un-cheatable random flags.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup"); p.add_argument("--dir", default="~/ctfdrill"); p.set_defaults(func=cmd_setup)
    p = sub.add_parser("serve"); p.add_argument("--dir", default="~/ctfdrill")
    p.add_argument("--port", type=int, default=8899); p.set_defaults(func=cmd_serve)
    p = sub.add_parser("verify"); p.add_argument("--dir", default="~/ctfdrill")
    p.add_argument("challenge"); p.add_argument("flag"); p.set_defaults(func=cmd_verify)
    args = ap.parse_args()
    args.dir = os.path.expanduser(args.dir)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
