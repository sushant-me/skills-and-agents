#!/usr/bin/env python3
"""ctfready - one command that answers "am I actually ready to start?".

Before an event you want a single go/no-go, not six commands you have to remember
in order while a clock is running. This runs the whole preparation chain and
prints one report:

  1. toolchain preflight     - can this machine do the work at all?
  2. technique rehearsal     - do the documented techniques actually execute?
  3. platform recon          - is each event reachable, am I registered, when
                               does it start, and is the CSRF scrape working?

Exit code 0 only when nothing is blocking.

Usage:
    ctfready.py --target https://ctf.cyberleague.co --cookie "session=..." \
                --target https://ctf.xposedornot.com  --cookie "session=..." \
                [--quick]

    --quick   skip the rehearsal (seconds instead of ~1 minute)

Cookies pair with targets by position; a target without a cookie is still
checked, just anonymously.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.expanduser("~/.ctf/venv/bin/python")


def py() -> str:
    """Prefer the CTF venv - the system python lacks most of the toolchain."""
    return VENV_PY if os.path.exists(VENV_PY) else sys.executable


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"
    except Exception as e:
        return 1, "EXC %s" % e


def section(title: str) -> None:
    print("\n" + "─" * 70)
    print(title)
    print("─" * 70)


def main() -> int:
    ap = argparse.ArgumentParser(description="One-command CTF readiness check.")
    ap.add_argument("--target", action="append", default=[],
                    help="platform URL (repeatable)")
    ap.add_argument("--cookie", action="append", default=[],
                    help="Cookie header for the preceding target (repeatable)")
    ap.add_argument("--quick", action="store_true", help="skip the rehearsal")
    ap.add_argument("--ledger", default=os.path.expanduser("~/ctf/ledger.json"))
    a = ap.parse_args()

    blockers: list[str] = []
    warnings: list[str] = []

    print("=" * 70)
    print("CTF READINESS  ·  %s" % datetime.now(timezone.utc).strftime("%a %d %b %Y %H:%M UTC"))
    print("=" * 70)

    # 1 ------------------------------------------------------------- toolchain
    section("1. TOOLCHAIN")
    rc, out = run([py(), os.path.join(HERE, "ctfpreflight.py")], timeout=300)
    for line in out.splitlines():
        if line.startswith(("CLI tools present", "Python modules present", "MISSING", "CRITICAL")):
            print("   " + line)
    if rc != 0:
        blockers.append("toolchain: a CRITICAL tool is missing")
        print("   ✗ critical tool missing")
    else:
        print("   ✓ no critical gaps")

    # 2 ------------------------------------------------------------- rehearsal
    if a.quick:
        section("2. REHEARSAL  (skipped - --quick)")
    else:
        section("2. REHEARSAL  (proving the techniques execute)")
        rc, out = run([py(), os.path.join(HERE, "ctfrehearsal.py")], timeout=900)
        res = [l for l in out.splitlines() if "RESULT:" in l]
        fails = [l.strip() for l in out.splitlines() if l.strip().startswith("- ")]
        print("   " + (res[0].strip() if res else "no result line"))
        for f in fails:
            print("   ✗ " + f)
        if rc != 0:
            blockers.append("rehearsal: %d drill(s) failing" % len(fails))
        else:
            print("   ✓ every documented technique executes here")

    # 3 -------------------------------------------------------------- platform
    section("3. PLATFORMS")
    if not a.target:
        warnings.append("no --target given; platform state unchecked")
        print("   (no targets supplied)")
    for i, url in enumerate(a.target):
        ck = a.cookie[i] if i < len(a.cookie) else None
        print("\n   %s" % url)
        # --url/--cookie are TOP-LEVEL flags on ctfctfd.py: they must precede
        # the subcommand. Appending them after "recon" makes argparse reject the
        # whole invocation.
        cmd = [py(), os.path.join(HERE, "ctfctfd.py"), "--url", url]
        if ck:
            cmd += ["--cookie", ck]
        cmd += ["recon"]
        rc, out = run(cmd, timeout=120)
        printed = 0
        for line in out.splitlines():
            s = line.strip()
            if not s or s.startswith("=") or s.startswith("CTFd RECON"):
                continue
            if s.startswith(("user", "email", "mode", "team", "csrfNonce",
                             "START", "END", "->", "/api/")):
                print("      " + s)
                printed += 1
        if printed == 0:
            # Never print nothing: a silent section is worse than a noisy one,
            # because it reads as "fine" when it means "the probe failed".
            print("      ! recon produced no parsable output (rc=%s)" % rc)
            for line in out.splitlines()[:8]:
                print("        | " + line.strip())
            blockers.append("%s: recon failed (rc=%s)" % (url, rc))
        if "csrfNonce : present" in out:
            print("      ✓ CSRF scrape works (submission path is viable)")
        elif "csrfNonce : MISSING" in out:
            blockers.append("%s: csrfNonce not scraped - submits will fail" % url)
            print("      ✗ CSRF nonce not found")
        if "401" in out and "users/me" in out:
            warnings.append("%s: not authenticated (cookie stale?)" % url)

    # ------------------------------------------------------------- summary
    section("VERDICT")
    if blockers:
        print("   NO-GO — blocking:")
        for b in blockers:
            print("     ✗ " + b)
    else:
        print("   GO — nothing blocking.")
    if warnings:
        print("   Caveats:")
        for w in warnings:
            print("     ! " + w)
    print("\n   Next: at T-15min, re-run `recon` per platform to confirm the window,")
    print("         then submit only through ctfctfd.py with --verified.\n")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
