#!/usr/bin/env python3
"""ctfctfd_mock - a CTFd-faithful target for rehearsing the CTFd client.

Before an event, the one thing you cannot afford to discover mid-round is that
your submission client does not actually work against the platform's contract.
This serves CTFd's real shapes so `ctfctfd.py` can be exercised end to end:

  * `GET /` emits `window.init = {...}` with a **csrfNonce** - the value CTFd
    requires on every POST, and the single most common reason a submit fails in
    a way that looks like a wrong flag.
  * `GET /api/v1/challenges` returns **403 before the start** and the list after.
  * `POST /api/v1/challenges/attempt` **enforces the CSRF header** and answers
    with CTFd's status-coded body:
    `{"success":true,"data":{"status":"correct|incorrect|already_solved|paused|ratelimited"}}`
  * A POST before the start returns a **bare `{"message":...}` with no `data`** -
    the refusal shape that must not be read as "wrong".

Usage:
    ctfctfd_mock.py --port 8897 [--live] [--ratelimit-every N]
    open http://127.0.0.1:8897/ and copy csrfNonce, or let ctfctfd.py scrape it
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time

CHALLENGES = [
    {"id": 1, "name": "rehearsal-alpha", "category": "recon",   "value": 250},
    {"id": 2, "name": "rehearsal-beta",  "category": "osint",   "value": 250},
    {"id": 3, "name": "rehearsal-gamma", "category": "forensics", "value": 250},
]
FLAGS = {
    1: "Null0rigin{mock_recon_flag}",
    2: "Null0rigin{mock_osint_flag}",
    3: "Null0rigin{mock_forensics_flag}",
}


def load_drill(drill_dir: str):
    """Serve a generated drill's own challenges, so the rehearsal exercises the
    real solve -> submit path rather than fixed placeholder flags.

    Note the id type: the drill names challenges with strings, while CTFd uses
    integers. Mapping here is deliberate - the client has to cope with a string
    challenge reference, and that mismatch is exactly the kind of thing that
    only shows up when the two halves are wired together.
    """
    import os
    ch = json.load(open(os.path.join(drill_dir, "CHALLENGES.json")))
    key = json.load(open(os.path.join(drill_dir, ".answerkey.json")))
    out, flags = [], {}
    for i, c in enumerate(ch, start=1):
        out.append({"id": i, "name": c["name"], "category": c["category"],
                    "value": c["points"]})
        flags[i] = key[c["name"]]
    return out, flags


def build(csrf: str, start: int, end: int, live: bool,
          rate_every: int = 0, challenges=None, flags=None):
    from flask import Flask, request, Response

    app = Flask("ctfctfd_mock")
    state = {"solved": set(), "attempts": 0}
    CH = challenges if challenges else CHALLENGES
    FL = flags if flags else FLAGS

    @app.get("/")
    def index():
        init = {
            "urlRoot": "", "csrfNonce": csrf, "userMode": "teams",
            "userId": 4242, "userName": "rehearsal", "userEmail": "r@example.test",
            "userVerified": True, "teamId": 99, "teamName": "rehearsal-team",
            "start": start, "end": end,
        }
        blob = json.dumps(init, separators=(",", ":")).replace('"', "'")
        # Mirrors CTFd's own embedding, which is what the client scrapes.
        html = ("<!doctype html><html><head><title>rehearsal CTFd</title>"
                "<script>window.init = " + blob + ";</script></head>"
                "<body><h1>rehearsal CTFd</h1></body></html>")
        return Response(html, mimetype="text/html")

    @app.get("/api/v1/users/me")
    def users_me():
        return {"success": True, "data": {
            "id": 4242, "name": "rehearsal", "email": "r@example.test",
            "team_id": 99, "verified": True}}

    @app.get("/api/v1/teams/me")
    def teams_me():
        return {"success": True, "data": {
            "id": 99, "name": "rehearsal-team", "members": [4242, 4243],
            "captain_id": 4242}}

    def started() -> bool:
        return live or time.time() >= start

    @app.get("/api/v1/challenges")
    def challenges():
        if not started():
            return {"message": "rehearsal CTFd has not started yet"}, 403
        return {"success": True, "data": [
            dict(c, solved_by_me=(c["id"] in state["solved"])) for c in CH]}

    @app.post("/api/v1/challenges/attempt")
    def attempt():
        # CTFd rejects a POST whose CSRF header is missing or wrong.
        tok = request.headers.get("CSRF-Token") or request.headers.get("X-CSRF-Token")
        if not tok or tok != csrf:
            return {"message": "CSRF token is missing or invalid"}, 403
        if not started():
            # The refusal shape: a bare message, NO `data` key.
            return {"message": "You don't have the permission to access the "
                               "requested resource."}, 403
        body = request.get_json(force=True, silent=True) or {}
        cid, sub = body.get("challenge_id"), body.get("submission")
        if cid not in FL:
            return {"success": False, "errors": ["challenge not found"]}, 404
        if cid in state["solved"]:
            return {"success": True, "data": {"status": "already_solved",
                                              "message": "You already solved this"}}
        state["attempts"] += 1
        if rate_every and state["attempts"] % rate_every == 0:
            return {"success": True, "data": {"status": "ratelimited",
                                              "message": "You're submitting too fast"}}
        if sub == FL[cid]:
            state["solved"].add(cid)
            return {"success": True, "data": {"status": "correct",
                                              "message": "Correct!"}}
        return {"success": True, "data": {"status": "incorrect",
                                          "message": "Incorrect"}}

    return app


def main() -> int:
    ap = argparse.ArgumentParser(description="CTFd-faithful mock for rehearsing ctfctfd.py")
    ap.add_argument("--port", type=int, default=8897)
    ap.add_argument("--live", action="store_true", help="pretend the event has started")
    ap.add_argument("--ratelimit-every", type=int, default=0,
                    help="return 'ratelimited' every Nth attempt")
    ap.add_argument("--csrf", default=None, help="pin the nonce (default: random)")
    ap.add_argument("--drill-dir", default=None,
                    help="serve a ctfdrill-generated set instead of the built-in placeholders")
    a = ap.parse_args()

    csrf = a.csrf or secrets.token_hex(32)
    start = int(time.time()) - 60 if a.live else int(time.time()) + 3600
    end = start + 86400
    ch, fl = (load_drill(a.drill_dir) if a.drill_dir else (None, None))
    app = build(csrf, start, end, a.live, a.ratelimit_every, ch, fl)
    print("mock CTFd on http://127.0.0.1:%d  (live=%s)" % (a.port, a.live))
    print("csrfNonce (also served in the page): %s" % csrf)
    print("challenges: %s" % ", ".join("%d=%s" % (c["id"], c["name"]) for c in (ch or CHALLENGES)))
    app.run(port=a.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
