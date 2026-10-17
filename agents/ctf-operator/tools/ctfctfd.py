#!/usr/bin/env python3
"""ctfctfd - a CTFd client that knows the platform's rules before you need them.

Both of tomorrow's events run CTFd, which behaves differently from a bespoke
platform in three ways that quietly cost time if you meet them mid-event:

  * **Every POST needs a CSRF nonce.** CTFd embeds it in the page as
    `window.init.csrfNonce`. A request without it fails in a way that looks like
    a wrong flag. This tool scrapes it for you.
  * **Submissions are status-coded, not boolean.** The response is
    `{"success":true,"data":{"status":...}}` where status is one of
    correct / incorrect / already_solved / paused / ratelimited. Treating
    "paused" as "wrong" is a real way to waste an attempt budget.
  * **The challenge list is hidden before the start** and returns
    `403 {"message": "... has not started yet"}` — not an error you caused.

It shares the ledger and the verification gate with `ctfsub.py`, so the two
clients behave identically where it matters.

Usage:
    ctfctfd.py --url https://ctf.example.com recon
    ctfctfd.py --url https://ctf.example.com --cookie "session=..." list
    ctfctfd.py --url ... --cookie ... --ledger ~/ctf/ledger.json \
        submit <challenge_id> '<flag>' --verified "how you got it"
    ctfctfd.py --url ... --cookie ... status
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


# --------------------------------------------------------------- session ----

class Ctfd:
    def __init__(self, base: str, cookie: str | None = None, timeout: int = 30):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        # Accept a raw "k=v; k2=v2" cookie header, which is what a browser
        # DevTools "Copy as cURL" gives you.
        if cookie:
            self._load_cookie_header(cookie)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf: str | None = None
        self.init: dict = {}

    def _load_cookie_header(self, header: str) -> None:
        for part in header.split(";"):
            if "=" not in part:
                continue
            k, v = part.strip().split("=", 1)
            c = http.cookiejar.Cookie(
                version=0, name=k, value=v, port=None, port_specified=False,
                domain=urllib.parse.urlparse(self.base).hostname or "",
                domain_specified=False, domain_initial_dot=False,
                path="/", path_specified=True, secure=self.base.startswith("https"),
                expires=None, discard=True, comment=None, comment_url=None,
                rest={}, rfc2109=False)
            self.jar.set_cookie(c)

    def request(self, method: str, path: str, data=None, raw_body=None,
                ctype="application/json"):
        url = self.base + path
        headers = {"Accept": "application/json",
                   "User-Agent": "Mozilla/5.0 (compatible; ctfctfd)"}
        body = None
        if raw_body is not None:
            body = raw_body.encode()
            headers["Content-Type"] = ctype
        elif data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = ctype
        if method == "POST" and self.csrf:
            # CTFd accepts either spelling; send both.
            headers["CSRF-Token"] = self.csrf
            headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            return -1, "EXC %s" % e

    def boot(self) -> dict:
        """Load the landing page and scrape CTFd's window.init block.

        This is where csrfNonce, the event window, and your user/team ids live.

        Themes differ in how they emit that block - one wraps it with the exact
        `window.init = {` ... `}` shape, another spaces or terminates it
        differently, and a minifier can move it entirely. So: try the block
        first, then fall back to scanning the whole document for the individual
        keys. Missing the nonce is the expensive failure, because CTFd rejects
        the POST in a way that looks like a wrong flag.
        """
        st, html = self.request("GET", "/")
        m = re.search(r"window\.init\s*=\s*\{(.*?)\n\s*\}", html, re.S)
        blob = m.group(1) if m else html
        out: dict = {}
        for km in re.finditer(
                r"['\"]?(\w+)['\"]?\s*:\s*(\d+|true|false|null|\"[^\"]*\"|'[^']*')", blob):
            k, v = km.group(1), km.group(2)
            if k in out:          # first occurrence wins
                continue
            if v in ("true", "false"):
                out[k] = (v == "true")
            elif v == "null":
                out[k] = None
            elif v.startswith(("'", '"')):
                out[k] = v[1:-1]
            else:
                try:
                    out[k] = int(v)
                except ValueError:
                    out[k] = v
        self.init = out
        self.csrf = out.get("csrfNonce")
        return out

    def api(self, path: str, data=None, method=None):
        st, txt = self.request(method or ("POST" if data is not None else "GET"),
                               path, data=data)
        try:
            return st, json.loads(txt)
        except Exception:
            return st, txt


# ---------------------------------------------------------------- ledger ----

def load_ledger(path: str) -> dict:
    if not os.path.exists(path):
        return {"version": 1, "attempts": [], "solved": {}, "attempts_left": {},
                "event_ended": False}
    with open(path) as fh:
        d = json.load(fh)
    for k, v in (("attempts", []), ("solved", {}), ("attempts_left", {})):
        d.setdefault(k, v)
    d.setdefault("event_ended", False)
    return d


def save_ledger(path: str, d: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def spent_on(d: dict, cid) -> int:
    return sum(1 for a in d["attempts"] if str(a.get("challenge")) == str(cid))


# ------------------------------------------------------------- classify -----

def classify_ctfd(body, status: int | None = None) -> str:
    """Map CTFd's response onto an action.

    CTFd answers in two shapes, and mixing them up is how an attempt gets
    burned. A real verdict arrives as `{"success":true,"data":{"status":...}}`.
    A refusal arrives as a bare `{"message":"..."}` with NO `data` - and before
    the event starts, or for a challenge you cannot see, that refusal is an
    HTTP 403 carrying a generic permission string. Treating that as "wrong"
    spends an attempt on a challenge that was never open.
    """
    if not isinstance(body, dict):
        if status == 401:
            return "auth_error"
        if status == 403:
            return "not_started"
        return "unknown"

    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    status_field = (data.get("status") or "").lower()
    msg = (data.get("message") or body.get("message") or "").lower()

    # A verdict about the flag.
    if status_field == "correct":
        return "correct"
    if status_field == "already_solved":
        return "already_solved"
    if status_field in ("paused", "ratelimited"):
        return "rate_limited"
    if status_field == "incorrect":
        if "too fast" in msg or "rate" in msg or "paused" in msg or "wait" in msg:
            return "rate_limited"
        return "wrong"

    # A refusal - no `data`, so this was never a judgement on the flag.
    if "not started yet" in msg or "has not started" in msg:
        return "not_started"
    if status == 401 or "authentication" in msg or "must be logged in" in msg:
        return "auth_error"
    if status == 403 or "permission" in msg or "read-protected" in msg:
        return "not_started"
    return "unknown"


# ----------------------------------------------------------------- verbs ----

def local(ts):
    if not ts:
        return "-"
    d = datetime.fromtimestamp(int(ts), timezone.utc)
    if ZoneInfo:
        try:
            d = d.astimezone(ZoneInfo("Asia/Kathmandu"))
            return d.strftime("%a %d %b %I:%M %p NPT")
        except Exception:
            pass
    return d.strftime("%a %d %b %H:%M UTC")


def cmd_recon(a) -> int:
    c = Ctfd(a.url, a.cookie)
    init = c.boot()
    print("=" * 68)
    print("CTFd RECON  %s" % a.url)
    print("=" * 68)
    if not init:
        print("  window.init not found - is this CTFd, and are you logged in?")
    # Themes vary in what they embed; the API is authoritative for identity.
    ust, ubody = c.api("/api/v1/users/me")
    tst, tbody = c.api("/api/v1/teams/me")
    u = (ubody.get("data") if isinstance(ubody, dict) else None) or {}
    t = (tbody.get("data") if isinstance(tbody, dict) else None) or {}
    user = init.get("userName") or u.get("name") or "?"
    uid = init.get("userId") or u.get("id") or "?"
    email = init.get("userEmail") or u.get("email") or "-"
    verified = init.get("userVerified")
    if verified is None:
        verified = u.get("verified")
    team = init.get("teamName") or t.get("name") or "(no team)"
    tid = init.get("teamId") or t.get("id") or "-"
    members = t.get("members")
    print("  user      : %s (id %s)" % (user, uid))
    print("  email     : %s   verified=%s" % (email, verified))
    print("  mode      : %s" % (init.get("userMode") or u.get("mode") or "-"))
    print("  team      : %s (id %s)%s" % (
        team, tid, "" if not members else "  members=%d" % len(members)))
    print("  csrfNonce : %s" % ("present (%d chars)" % len(c.csrf or "") if c.csrf else "MISSING"))
    print("  START     : %s" % local(init.get("start")))
    print("  END       : %s" % local(init.get("end")))
    if init.get("start") and init.get("end"):
        now = datetime.now(timezone.utc).timestamp()
        if now < init["start"]:
            print("  -> starts in %s" % str(datetime.fromtimestamp(init["start"], timezone.utc)
                                           - datetime.now(timezone.utc)).split(".")[0])
        elif now > init["end"]:
            print("  -> EVENT HAS ENDED")
        else:
            print("  -> LIVE now, %s remaining" % str(datetime.fromtimestamp(init["end"], timezone.utc)
                                                      - datetime.now(timezone.utc)).split(".")[0])
    for path in ("/api/v1/challenges", "/api/v1/scoreboard/top/10", "/api/v1/notifications"):
        st, body = c.api(path)
        n = len(body.get("data", [])) if isinstance(body, dict) and isinstance(body.get("data"), list) else None
        extra = ""
        if isinstance(body, dict):
            extra = (body.get("message") or "")[:60]
        print("  %-30s %s %s%s" % (path, st, ("items=%d " % n) if n is not None else "", extra))
    return 0


def cmd_list(a) -> int:
    c = Ctfd(a.url, a.cookie)
    c.boot()
    st, body = c.api("/api/v1/challenges")
    if not isinstance(body, dict) or not body.get("success"):
        print("challenges unavailable: %s %s" % (st, str(body)[:200]))
        return 1
    rows = body.get("data") or []
    if not rows:
        print("no challenges visible yet")
        return 0
    rows.sort(key=lambda r: (r.get("category") or "", r.get("value") or 0))
    print("%-6s %-10s %-5s %-6s %s" % ("id", "category", "pts", "solved", "name"))
    for r in rows:
        print("%-6s %-10s %-5s %-6s %s" % (r.get("id"), (r.get("category") or "")[:10],
                                           r.get("value"), r.get("solved_by_me"), r.get("name")))
    print("\n%d challenges, %d solved by you" % (len(rows), sum(1 for r in rows if r.get("solved_by_me"))))
    return 0


def cmd_submit(a) -> int:
    if not a.verified and not a.unverified:
        print("REFUSING: state how this flag was verified.\n"
              "  --verified \"<how>\"   or   --unverified")
        return 2
    if a.unverified:
        print("!! UNVERIFIED SUBMISSION - the pattern events penalise.")

    c = Ctfd(a.url, a.cookie)
    c.boot()
    if not c.csrf:
        print("WARNING: no csrfNonce scraped; POST may be rejected. Pass --cookie.")

    d = load_ledger(a.ledger)
    if d.get("event_ended"):
        print("REFUSING: ledger says the event has ended.")
        return 2
    if str(a.challenge) in {str(k) for k in d["solved"]}:
        print("ALREADY SOLVED (ledger): %s" % a.challenge)
        return 0
    left = d["attempts_left"].get(str(a.challenge))
    if left is not None and left <= 0:
        print("REFUSING: attemptsLeft=0 recorded for %s." % a.challenge)
        return 2

    print("spent so far on %s: %d" % (a.challenge, spent_on(d, str(a.challenge))))
    try:
        cid = int(a.challenge)
    except ValueError:
        cid = a.challenge
    st, body = c.api("/api/v1/challenges/attempt",
                     {"challenge_id": cid, "submission": a.flag})
    outcome = classify_ctfd(body, st)

    d["attempts"].append({"challenge": str(a.challenge), "flag": a.flag, "http": st,
                          "outcome": outcome,
                          "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "verified": a.verified or ("UNVERIFIED" if a.unverified else None)})
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        if isinstance(body["data"].get("attempts_left"), int):
            d["attempts_left"][str(a.challenge)] = body["data"]["attempts_left"]

    if outcome == "correct":
        d["solved"][str(a.challenge)] = a.flag
        print("CORRECT  %s" % (body.get("data", {}).get("message", "")))
        save_ledger(a.ledger, d); return 0
    if outcome == "already_solved":
        d["solved"][str(a.challenge)] = a.flag
        print("ALREADY SOLVED (server)."); save_ledger(a.ledger, d); return 0
    if outcome == "rate_limited":
        save_ledger(a.ledger, d)
        print("PAUSED / RATE LIMITED - this is NOT a wrong flag. Back off.")
        time.sleep(10); return 3
    if outcome == "not_started":
        save_ledger(a.ledger, d)
        print("EVENT NOT STARTED - nothing to submit yet.")
        return 2
    if outcome == "auth_error":
        save_ledger(a.ledger, d)
        print("AUTH ERROR - refresh the session cookie before spending another attempt.")
        return 3

    save_ledger(a.ledger, d)
    msg = ""
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        msg = body["data"].get("message") or ""
    print("WRONG. %s" % msg)
    return 1


def cmd_status(a) -> int:
    d = load_ledger(a.ledger)
    print("event_ended : %s" % d.get("event_ended"))
    print("solved      : %d" % len(d["solved"]))
    for k, v in sorted(d["solved"].items()):
        print("   %-8s %s" % (k, v))
    print("attempts    : %d" % len(d["attempts"]))
    for x in d["attempts"]:
        print("   %-8s %-14s %s" % (x.get("challenge"), x.get("outcome"), x.get("at")))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CTFd client with CSRF handling and a hard ledger.")
    ap.add_argument("--url", required=True, help="platform root, e.g. https://ctf.example.com")
    ap.add_argument("--cookie", default=os.environ.get("CTF_COOKIE"),
                    help="raw Cookie header from the browser (session=...)")
    ap.add_argument("--ledger", default=os.path.expanduser("~/ctf/ledger.json"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("recon").set_defaults(func=cmd_recon)
    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p = sub.add_parser("submit")
    p.add_argument("challenge")
    p.add_argument("flag")
    p.add_argument("--verified", metavar="HOW")
    p.add_argument("--unverified", action="store_true")
    p.set_defaults(func=cmd_submit)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
