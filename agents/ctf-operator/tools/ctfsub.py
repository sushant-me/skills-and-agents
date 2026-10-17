#!/usr/bin/env python3
"""ctfsub - a submission client that will not let you lose points you earned.

Design rules (each one is a mistake that has cost a real event):

  * ONE request at a time. Never parallel. On lockout-protected endpoints every
    failed attempt extends the lock, and a burst can push it past the event end.
  * A hard ledger. Every attempt is written before the next is allowed, so an
    attempt cannot be double-spent or forgotten across sessions.
  * Server-reported budgets win. If the platform says attemptsLeft=N, that is
    the truth and the ledger is corrected to match.
  * Rate limits are respected, not raced. On a "wait Ns" response it sleeps.
  * eventEnded stops everything. No further submissions, ever.

Usage:
    ctfsub.py --url <submit-endpoint> --token <bearer> \
              --ledger ~/ctf/ledger.json submit <challenge_id> <flag>

    ctfsub.py --ledger ~/ctf/ledger.json status
    ctfsub.py --ledger ~/ctf/ledger.json spent <challenge_id>

The endpoint and token are whatever the site's own frontend uses - capture them
from devtools rather than guessing. This tool is for YOUR account's own
submissions against YOUR team's challenges.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

LEDGER_VERSION = 1
DEFAULT_BACKOFF = 10.0


# ---------------------------------------------------------------- ledger ----

def load_ledger(path: str) -> dict:
    if not os.path.exists(path):
        return {"version": LEDGER_VERSION, "attempts": [], "solved": {},
                "attempts_left": {}, "event_ended": False}
    with open(path) as fh:
        data = json.load(fh)
    data.setdefault("attempts", [])
    data.setdefault("solved", {})
    data.setdefault("attempts_left", {})
    data.setdefault("event_ended", False)
    return data


def save_ledger(path: str, data: dict) -> None:
    """Atomic write - a torn ledger is worse than no ledger."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def spent_on(data: dict, cid: str) -> int:
    return sum(1 for a in data["attempts"] if a.get("challenge") == cid)


# ------------------------------------------------------------- transport ----

def post_json(url: str, token: str | None, payload: dict, timeout: int = 30) -> tuple[int, dict | str]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except Exception as exc:  # network wobble
        return -1, "transport error: %s" % exc
    try:
        return status, json.loads(raw)
    except Exception:
        return status, raw


def classify(status: int, body) -> str:
    """Map a submit response onto an outcome we can act on.

    Order matters. A rate-limit body frequently ALSO carries "correct": false,
    so throttle signals must be tested BEFORE the generic wrong-answer branch -
    otherwise a throttled request is burned into the ledger as a real miss and
    the attempt accounting silently drifts.
    """
    if status == -1:
        return "transport_error"

    if isinstance(body, dict):
        # Terminal states first: unambiguous, and never a wrong flag.
        if body.get("eventEnded"):
            return "event_ended"
        if body.get("alreadySolved"):
            return "already_solved"
        if body.get("correct") is True:
            return "correct"

        # Throttle signals BEFORE "wrong": a rate-limited response is not an
        # answer about the flag at all.
        blob = json.dumps(body).lower()
        if (isinstance(body.get("retryAfter"), (int, float))
                or "too fast" in blob or "too many" in blob
                or "retry" in blob or "wait" in blob):
            return "rate_limited"

        if body.get("correct") is False:
            return "wrong"

    # 429 Too Many Requests and 428 Precondition Required (a throttle middleware
    # demanding a retry proof) both mean "not an answer about the flag".
    if status in (429, 428):
        return "rate_limited"
    if status in (401, 403):
        return "auth_error"
    return "unknown"


# ---------------------------------------------------------------- verbs ----

def cmd_submit(args) -> int:
    # --- credibility gate -------------------------------------------------
    # Many events (Null Origin and Cyber League among them) penalise
    # "hallucinated exploits or invalid automated data generated by AI" with a
    # Credibility Score that acts as a tie-breaker and a multiplier on total
    # points. A hallucinated flag can therefore cost far more than the flag it
    # missed, so submission requires a conscious claim about verification.
    if not args.verified and not args.unverified:
        print("REFUSING: state how this flag was verified.\n"
              "  --verified \"<how>\"   e.g. 'round-trips against the ciphertext'\n"
              "  --unverified         only if you accept the credibility penalty\n"
              "A wrong flag is a normal loss; a confident invented one is worse.")
        return 2
    if args.unverified:
        print("!! UNVERIFIED SUBMISSION - this is the pattern events penalise.")
        print("!! Credibility scores act as tie-breakers and points multipliers.")

    data = load_ledger(args.ledger)

    if data.get("event_ended"):
        print("REFUSING: the event has ended (recorded in ledger). Nothing scores now.")
        return 2

    if args.challenge in data["solved"]:
        print("ALREADY SOLVED (ledger): %s = %s" % (args.challenge, data["solved"][args.challenge]))
        return 0

    left = data["attempts_left"].get(args.challenge)
    if left is not None and left <= 0:
        print("REFUSING: server reported attemptsLeft=0 for %s. Do not probe further."
              % args.challenge)
        return 2

    # One attempt. Always one.
    print("spent so far on %s: %d%s"
          % (args.challenge, spent_on(data, args.challenge),
             "" if left is None else "  (server says %d left)" % left))

    status, body = post_json(args.url, args.token, {"challengeId": args.challenge, "flag": args.flag})
    outcome = classify(status, body)

    entry = {"challenge": args.challenge, "flag": args.flag, "status": status,
             "outcome": outcome, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "verified": args.verified or ("UNVERIFIED" if args.unverified else None)}
    data["attempts"].append(entry)

    if isinstance(body, dict) and isinstance(body.get("attemptsLeft"), int):
        data["attempts_left"][args.challenge] = body["attemptsLeft"]

    if outcome == "correct":
        data["solved"][args.challenge] = args.flag
        print("CORRECT  +%s" % body.get("points", "?"))
        save_ledger(args.ledger, data)
        return 0
    if outcome == "already_solved":
        data["solved"][args.challenge] = args.flag
        print("ALREADY SOLVED (server). Not a failure - your notes were stale.")
        save_ledger(args.ledger, data)
        return 0
    if outcome == "event_ended":
        data["event_ended"] = True
        save_ledger(args.ledger, data)
        print("EVENT ENDED. Ledger marked closed; no further submissions.")
        return 2
    if outcome == "rate_limited":
        delay = DEFAULT_BACKOFF
        if isinstance(body, dict) and isinstance(body.get("retryAfter"), (int, float)):
            delay = float(body["retryAfter"]) + 1
        save_ledger(args.ledger, data)
        print("RATE LIMITED. Sleeping %.0fs then you may retry ONCE." % delay)
        time.sleep(delay)
        return 3
    if outcome == "auth_error":
        save_ledger(args.ledger, data)
        print("AUTH ERROR (%s). Refresh the token before spending another attempt." % status)
        return 3
    if outcome == "transport_error":
        save_ledger(args.ledger, data)
        print("TRANSPORT ERROR - the attempt may or may not have landed. Check `status` "
              "before retrying; do not blind-retry a lockout-protected target.")
        return 3

    print("WRONG. %s" % ("" if left is None else "server reports %s left" % body.get("attemptsLeft")
                         if isinstance(body, dict) else ""))
    save_ledger(args.ledger, data)
    return 1


def cmd_status(args) -> int:
    data = load_ledger(args.ledger)
    print("event_ended : %s" % data.get("event_ended"))
    print("solved      : %d" % len(data["solved"]))
    for cid, flag in sorted(data["solved"].items()):
        print("   %-28s %s" % (cid, flag))
    print("attempts    : %d total" % len(data["attempts"]))
    counts: dict[str, int] = {}
    for a in data["attempts"]:
        counts[a["challenge"]] = counts.get(a["challenge"], 0) + 1
    for cid, n in sorted(counts.items()):
        left = data["attempts_left"].get(cid)
        print("   %-28s %d spent%s" % (cid, n, "" if left is None else ", %d left" % left))
    return 0


def cmd_spent(args) -> int:
    data = load_ledger(args.ledger)
    print("%d" % spent_on(data, args.challenge))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CTF submission client with a hard attempt ledger.")
    ap.add_argument("--ledger", default=os.path.expanduser("~/ctf/ledger.json"))
    ap.add_argument("--url", default=os.environ.get("CTF_SUBMIT_URL"),
                    help="submit endpoint (capture it from the site's own frontend)")
    ap.add_argument("--token", default=os.environ.get("CTF_TOKEN"),
                    help="session bearer token (prefer the env var over argv)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("submit")
    p.add_argument("challenge")
    p.add_argument("flag")
    p.add_argument("--verified", metavar="HOW",
                   help="how the flag was reproduced/verified (required unless --unverified)")
    p.add_argument("--unverified", action="store_true",
                   help="submit without verification; accepts the credibility penalty")
    p.set_defaults(func=cmd_submit)

    sub.add_parser("status").set_defaults(func=cmd_status)
    p = sub.add_parser("spent")
    p.add_argument("challenge")
    p.set_defaults(func=cmd_spent)

    args = ap.parse_args()
    if args.cmd == "submit" and not args.url:
        ap.error("--url (or CTF_SUBMIT_URL) is required for submit")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
