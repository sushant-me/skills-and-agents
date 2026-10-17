#!/usr/bin/env python3
"""ctfnulltriage - screen a candidate flag before anyone submits it.

The NullOrigin board pays out on the reflex. Its own author counts 27
flag-shaped strings on the stego chain alone, most reachable in under a minute,
every one of them wrong, and several of them *the neighbouring stage's real flag*
with a single homoglyph swapped in. On a credibility-scored event a wrong
submission is worse than no submission.

This tool is the mechanical part of the elimination procedure, so the part that
needs judgement is the only part left to a human. For each candidate it answers:

  1. Prefix   - is the prefix byte-for-byte `Null0rigin`, or a homoglyph?
  2. Container- is it wrapped in a valid PL8 works entry (magic AND crc32)?
  3. Already held - is it a flag this team has already recovered?
  4. Documented - do the author's writeups label it a decoy, or name the stage
                  whose flag it actually is?

It never claims a flag is CORRECT. Three of the four checks can only clear a
candidate or convict it; a candidate that survives all four is eligible to
submit, which is not the same as right. On the stego chain the only real
confirmation is that the flag opens the next stage.

`--scan` is the other half, and the one that earns its keep at a final: sweep
every downloaded artifact for valid works entries. On a board that keeps the
container, that finds every channel the author shipped - and every stage's
8-byte share, in stage order, without knowing what any stage's mechanism is.

    ctfnulltriage.py 'Null0rigin{a_b_c}'
    ctfnulltriage.py --file candidates.txt --ledger ~/Work/ctf/NOTES.md
    ctfnulltriage.py --container stage33.png            # decode one artifact
    ctfnulltriage.py --scan ~/dl/nullorigin --ledger ~/Work/ctf/NOTES.md
    ctfnulltriage.py --reference /tmp/no-writeups --json 'NullOrigin{x}'

Exit code 0 when at least one candidate is eligible to submit, 2 when every
candidate was convicted or needs evidence, 1 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import zlib

CANON = "Null0rigin"
MAGIC = b"PL8"

# Characters that render like one another. A prefix that differs from CANON only
# inside one of these groups is the board's homoglyph decoy family.
CONFUSABLE_GROUPS = ("0Oo", "1lI|!i", "5S", "8B", "2Z", "6G9gq", "rn", "vv")

FLAG_RE = re.compile(r"[A-Za-z0-9_]{5,24}\{[^}\n]{1,160}\}")
DECOY_HINT = re.compile(
    r"decoy|not a flag|isn't a flag|is not a flag|fake|bait|trap|cruellest|"
    r"wrong|homoglyph|no works entry|bare string",
    re.IGNORECASE,
)
# The writeups announce the real flag as "**Flag:**" - inline, or as a label on
# its own line above a fenced block. A line that declares the flag is never read
# as a decoy label, so a real flag can never be convicted by prose that happens
# to contain the word "wrong" nearby.
FLAG_LABEL = re.compile(r"\*\*\s*flag\s*:?\s*\*\*", re.IGNORECASE)
DECOY_HEADING = re.compile(r"^\s*#{1,6}\s*[^\n]*decoy", re.IGNORECASE)


# --------------------------------------------------------------- primitives --

def split_flag(text: str) -> tuple[str, str]:
    """('Null0rigin', 'the_body') for a flag-shaped string."""
    i = text.find("{")
    return (text[:i], text[i + 1:-1]) if i >= 0 else (text, "")


def prefix_verdict(candidate: str) -> tuple[str, str]:
    """('canonical'|'homoglyph'|'wrong', detail)."""
    prefix, _ = split_flag(candidate)
    if prefix == CANON:
        return "canonical", "prefix is byte-for-byte %s" % CANON
    if len(prefix) != len(CANON):
        return "wrong", "prefix %r is %d chars, %s is %d" % (
            prefix, len(prefix), CANON, len(CANON))
    for i, (got, want) in enumerate(zip(prefix, CANON)):
        if got == want:
            continue
        for group in CONFUSABLE_GROUPS:
            if got in group and want in group:
                others = "".join(sorted(set(group) - {got, want}))
                return "homoglyph", ("index %d: found %r, expected %r - homoglyph "
                                     "family, decoy" % (i, got, want)
                                     + (", also %r" % others if others else ""))
        return "wrong", "index %d: found %r, expected %r" % (i, got, want)
    return "wrong", "prefix differs but no position did"


def parse_entries(blob: bytes) -> list[dict]:
    """Every valid works entry in a blob: magic AND crc32 must both pass."""
    found: list[dict] = []
    at = 0
    while True:
        at = blob.find(MAGIC, at)
        if at < 0:
            return found
        if at + 10 <= len(blob):
            version = blob[at + 3]
            length = struct.unpack("<H", blob[at + 4:at + 6])[0]
            crc = struct.unpack("<I", blob[at + 6:at + 10])[0]
            payload = blob[at + 10:at + 10 + length]
            if len(payload) == length and (zlib.crc32(payload) & 0xFFFFFFFF) == crc:
                item = {"offset": at, "version": version, "length": length,
                        "payload": payload}
                if b"\x1f" in payload:
                    flag, _, share = payload.partition(b"\x1f")
                    item["flag"] = flag.decode("latin-1")
                    item["share"] = share.hex()
                else:
                    item["flag"] = payload.decode("latin-1")
                    item["share"] = None
                found.append(item)
        at += 1


# The largest possible entry is a 10-byte header plus a u16 length, so a window
# with a 64 KiB + 10 overlap can never split one.
WINDOW = 1 << 22
OVERLAP = 65545
STAGE_IN_PATH = re.compile(r"(?:^|[/\\])(\d{2})[-_]")


def stage_of(path: str) -> "int | None":
    """The stage number in a downloaded path like 31-driftwood/plate.png."""
    m = STAGE_IN_PATH.search(path)
    return int(m.group(1)) if m else None


def scan_file(path: str, rel: str, window: int = WINDOW) -> list[dict]:
    """Every valid works entry in one file, without loading the file whole.

    This is the finals move: on a board that keeps the container, the container
    is a *searchable* oracle. Sweep every downloaded artifact once and you have
    every channel the author shipped, plus every share, before you know what any
    stage's mechanism is.
    """
    hits: list[dict] = []
    seen: set[int] = set()
    try:
        size = os.path.getsize(path)
    except OSError:
        return hits
    try:
        with open(path, "rb") as fh:
            carry = b""
            read_at = 0
            while True:
                chunk = fh.read(window)
                if not chunk:
                    break
                window_bytes = carry + chunk
                start = read_at - len(carry)
                for h in parse_entries(window_bytes):
                    absolute = start + h["offset"]
                    if absolute in seen:
                        continue
                    seen.add(absolute)
                    h["offset"] = absolute
                    hits.append(h)
                carry = window_bytes[-OVERLAP:]
                read_at += len(chunk)
    except OSError:
        return hits
    hits.sort(key=lambda h: h["offset"])
    for h in hits:
        h["file"] = rel
        h["size"] = size
        h["stage"] = stage_of(rel)
    return hits


def scan_paths(paths: list[str], max_bytes: int) -> tuple[list[dict], list[str]]:
    """Walk files and directories; return (entries, skipped-large reports)."""
    hits: list[dict] = []
    skipped: list[str] = []
    for root in paths:
        if os.path.isfile(root):
            walk = [(os.path.dirname(root) or ".", [], [os.path.basename(root)])]
        elif os.path.isdir(root):
            walk = os.walk(root)
        else:
            skipped.append("%s: no such file or directory" % root)
            continue
        for dirpath, _dirs, names in walk:
            for name in sorted(names):
                full = os.path.join(dirpath, name)
                try:
                    if os.path.getsize(full) > max_bytes:
                        skipped.append("%s: larger than the scan cap" % full)
                        continue
                except OSError:
                    continue
                hits += scan_file(full, os.path.relpath(full, os.path.dirname(root) or "."))
    hits.sort(key=lambda h: (h["stage"] if h["stage"] is not None else 999,
                             h["file"], h["offset"]))
    return hits, skipped


def read_flags(path: str) -> set[str]:
    """Every flag-shaped string in a text file (the team ledger)."""
    try:
        with open(path, "r", errors="replace") as fh:
            return set(FLAG_RE.findall(fh.read()))
    except OSError:
        return set()


def index_reference(root: str) -> dict[str, list[dict]]:
    """Documented flags and decoys from the author writeups, keyed by string.

    A hit is marked `declared` when the writeups present it as the stage's flag
    (`**Flag:**`, inline or as a label above a fenced block) and `decoy` when the
    surrounding line or nearest heading says so. Both labels come from the
    author's own text, not from our inference.
    """
    index: dict[str, list[dict]] = {}
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", errors="replace") as fh:
                    lines = fh.read().splitlines()
            except OSError:
                continue
            heading = ""
            pending_label = False
            for n, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    heading = line.strip("# ").strip()
                labelled = bool(FLAG_LABEL.search(line))
                hits = FLAG_RE.findall(line)
                if labelled and not hits:
                    pending_label = True       # "**Flag:**" above a code fence
                    continue
                declared = labelled or pending_label
                pending_label = False
                hint = bool(DECOY_HINT.search(line) or DECOY_HEADING.search(heading)
                            or DECOY_HINT.search(heading))
                for hit in hits:
                    index.setdefault(hit, []).append({
                        "file": os.path.relpath(path, root),
                        "line": n,
                        "heading": heading,
                        "declared": declared,
                        "decoy": hint and not declared,
                        "text": line.strip()[:160],
                    })
    return index


# ------------------------------------------------------------------ triage --

def triage(candidate: str, container_hits: dict[str, dict],
           ledger: set[str], reference: dict[str, list[dict]]) -> dict:
    """Conviction beats doubt: any single decisive check settles the verdict."""
    kind, detail = prefix_verdict(candidate)
    entry = container_hits.get(candidate)
    already = candidate in ledger
    refs = reference.get(candidate, [])
    ref_decoys = [r for r in refs if r["decoy"] and not r["declared"]]
    ref_declared = [r for r in refs if r["declared"]]
    ref_plain = [r for r in refs if not r["decoy"] and not r["declared"]]

    reasons: list[str] = []

    # 1. prefix (a decoy family on its own)
    if kind == "canonical":
        reasons.append("prefix: byte-for-byte %s" % CANON)
    else:
        reasons.append("prefix: " + detail)

    # 2. container (the only oracle: magic AND crc32)
    if entry is None:
        reasons.append("container: no valid PL8 works entry carries this string")
    else:
        reasons.append("container: valid PL8 entry at file offset %d (v%d, "
                       "%d bytes)" % (entry["offset"], entry["version"], entry["length"]))

    # 3. already held
    if already:
        reasons.append("ledger: this exact flag is already recorded")

    # 4. documented by the author
    if ref_decoys:
        r = ref_decoys[0]
        reasons.append("documented: writeups label it a decoy (%s:%d, %r)"
                       % (r["file"], r["line"], r["heading"]))
    elif ref_declared:
        r = ref_declared[0]
        reasons.append("documented: the writeups present this as the flag of "
                       "%r (%s:%d) - if you have not solved that stage you are "
                       "reading the answer key, not a result"
                       % (r["heading"] or r["file"], r["file"], r["line"]))
    elif ref_plain:
        r = ref_plain[0]
        reasons.append("documented: appears in the writeups under %r (%s:%d) - "
                       "check whether that stage is one you already hold"
                       % (r["heading"], r["file"], r["line"]))

    if kind != "canonical":
        verdict = "DECOY"
    elif ref_decoys:
        verdict = "DECOY"
    elif already:
        verdict = "ALREADY-HELD"
    elif entry is None:
        verdict = "NEEDS-EVIDENCE"
    else:
        verdict = "ELIGIBLE"

    return {"candidate": candidate, "verdict": verdict, "prefix": kind,
            "container": entry is not None, "already_held": already,
            "reasons": reasons}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Screen candidate flags before submitting them.")
    ap.add_argument("candidates", nargs="*", help="candidate flag strings")
    ap.add_argument("--file", help="read candidates from a file, one per line")
    ap.add_argument("--container", action="append", default=[],
                    help="a downloaded artifact to parse for works entries "
                         "(repeatable)")
    ap.add_argument("--scan", action="append", default=[],
                    help="sweep a file or directory for every valid works entry "
                         "(repeatable) - the fastest way to find channels and "
                         "collect all six mordant shares")
    ap.add_argument("--max-mb", type=int, default=768,
                    help="skip files larger than this during --scan (default 768)")
    ap.add_argument("--ledger", help="team ledger to check already-held flags")
    ap.add_argument("--reference",
                    help="author writeups directory, for documented decoys")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    candidates = list(args.candidates)
    if args.file:
        try:
            with open(args.file, "r", errors="replace") as fh:
                candidates += [l.strip() for l in fh if l.strip()]
        except OSError as e:
            print("cannot read %s: %s" % (args.file, e), file=sys.stderr)
            return 1

    container_hits: dict[str, dict] = {}
    parsed: list[tuple[str, list[dict]]] = []
    for path in args.container:
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
        except OSError as e:
            print("cannot read %s: %s" % (path, e), file=sys.stderr)
            return 1
        hits = parse_entries(blob)
        parsed.append((path, hits))
        for h in hits:
            if h.get("flag"):
                container_hits.setdefault(h["flag"], h)
                candidates.append(h["flag"])

    sweep: list[dict] = []
    skipped: list[str] = []
    if args.scan:
        sweep, skipped = scan_paths(args.scan, args.max_mb * 1024 * 1024)
        # Annotate every swept entry with its own prefix verdict. Stage 37 ships
        # a poisoned entry - correct magic, correct CRC - whose flag is a
        # homoglyph of stage 36's and whose trailing bytes are a fake SEVENTH
        # share. The container check says yes to it; the prefix audit says no,
        # and that is the difference between the inner lock opening and not.
        for h in sweep:
            if h.get("flag"):
                h["prefix"], h["prefix_detail"] = prefix_verdict(h["flag"])
                container_hits.setdefault(h["flag"], h)
                candidates.append(h["flag"])

    if parsed and not args.json:
        for path, hits in parsed:
            print("%s: %d valid works entr%s" %
                  (path, len(hits), "y" if len(hits) == 1 else "ies"))
            for h in hits:
                print("  offset %-9d v%d  len %-6d share %s  %s"
                      % (h["offset"], h["version"], h["length"],
                         h["share"] or "-", h.get("flag", "")[:60]))

    if sweep and not args.json:
        print("SWEEP: %d valid works entr%s across %d scanned location(s)"
              % (len(sweep), "y" if len(sweep) == 1 else "ies", len(args.scan)))
        print("%-38s %-10s %-5s %-6s %-9s %s"
              % ("FILE", "OFFSET", "STAGE", "SHARE", "PREFIX", "FLAG"))
        for h in sweep:
            print("%-38s %-10d %-5s %-6s %-9s %s"
                  % (h["file"][-38:], h["offset"],
                     h["stage"] if h["stage"] is not None else "-",
                     (h["share"] or "-"),
                     h.get("prefix", "?"), h.get("flag", "")[:44]))
        for note in skipped:
            print("  skipped %s" % note)

        per_file: dict[str, int] = {}
        for h in sweep:
            per_file[h["file"]] = per_file.get(h["file"], 0) + 1
        multi = [f for f, n in per_file.items() if n > 1]
        if multi:
            print("\nnote: %d artifact(s) carry more than one valid entry (%s)."
                  % (len(multi), ", ".join(m[-38:] for m in multi)))
            print("  On this board that is the shape of the stage-37 poisoned "
                  "entry: correct magic, correct CRC, a homoglyph flag, and a")
            print("  fake SEVENTH share. Trust the entries whose prefix column "
                  "reads 'canonical', and check each one's flag against stage "
                  "36's before using its share.")

        good = [h for h in sweep if h.get("share") and h.get("prefix") == "canonical"]
        poisoned = [h for h in sweep if h.get("share") and h.get("prefix") != "canonical"]
        if poisoned:
            print("\nREJECTED %d share(s) on the prefix audit - do not use these:"
                  % len(poisoned))
            for h in poisoned:
                print("  %s @ %d  share %s  (%s)"
                      % (h["file"][-38:], h["offset"], h["share"],
                         h.get("prefix_detail", "")))
        if good:
            ordered = sorted(good, key=lambda h: (h["stage"] is None, h["stage"]))
            print("\nSHARES COLLECTED: %d" % len(ordered))
            for h in ordered:
                print("  stage %-4s %s   (%s @ %d)"
                      % (h["stage"] if h["stage"] is not None else "?", h["share"],
                         h["file"], h["offset"]))
            if len(ordered) == 6:
                print("  six shares, stage order: %s"
                      % " ".join(h["share"] for h in ordered))
                print("  if this is the same board, that is stage 37-mordant's "
                      "second argument set after stage 36's flag.")
            elif len(ordered) > 6:
                print("  %d shares for a six-share lock: re-check which stage "
                      "each file belongs to before using them." % len(ordered))

    if not candidates:
        ap.error("no candidates: pass strings, --file, --container, or --scan")

    ledger = read_flags(args.ledger) if args.ledger else set()
    reference = index_reference(args.reference) if args.reference else {}

    seen: set[str] = set()
    rows = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        rows.append(triage(c, container_hits, ledger, reference))

    if args.json:
        def public(h):
            return {k: v for k, v in h.items() if k != "payload"}
        print(json.dumps({"results": rows,
                          "sweep": [public(h) for h in sweep],
                          "skipped": skipped}, indent=2))
    else:
        print("\n%-6s %-14s %s" % ("VERDICT", "PREFIX", "CANDIDATE"))
        for r in rows:
            print("%-6s %-14s %s" % (r["verdict"], r["prefix"], r["candidate"][:70]))
        for r in rows:
            if r["verdict"] != "ELIGIBLE":
                print("\n%s" % r["candidate"][:90])
                for reason in r["reasons"]:
                    print("   - %s" % reason)
        held = [r for r in rows if r["verdict"] == "ELIGIBLE"]
        print("\n%d candidate(s): %d eligible to submit, %d convicted or "
              "unproven" % (len(rows), len(held), len(rows) - len(held)))
        if held:
            print("A surviving candidate is eligible, not confirmed: on the "
                  "stego chain the proof is that it opens the next stage.")

    return 0 if any(r["verdict"] == "ELIGIBLE" for r in rows) else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
