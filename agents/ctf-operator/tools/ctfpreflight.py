#!/usr/bin/env python3
"""ctfpreflight - know your toolchain before the clock starts.

Run this at the start of an event, and again if a tool behaves oddly. It reports
what is present, what is missing, and the exact command that fixes each gap.

Why this exists: a missing Python module or CLI tool discovered *mid-challenge*
costs far more than the two minutes this takes. Run it during preparation, not
during the event.

Usage:
    python3 ctfpreflight.py            # human-readable report
    python3 ctfpreflight.py --quiet    # only problems + exit code
Exit code 0 when every CRITICAL tool is present, 1 otherwise.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

# Tools whose absence will stop a whole category of challenge.
# (name, why it matters, how to fix)
CLI = [
    ("python3",    "everything",                     "system"),
    ("uv",         "installing the rest",            "https://astral.sh/uv"),
    ("file",       "identify artifacts",             "system"),
    ("strings",    "binutils - first look at a binary", "system"),
    ("readelf",    "binutils - ELF headers",         "system"),
    ("objdump",    "binutils - disassembly",         "system"),
    ("nm",         "binutils - symbols",             "system"),
    ("gdb",        "debugging",                      "system"),
    ("gcc",        "compiling PoCs and shells",      "system"),
    ("openssl",    "crypto primitives",              "system"),
    ("git",        "repos and history",              "system"),
    ("curl",       "HTTP",                           "system"),
    ("jq",         "JSON wrangling",                 "system"),
    ("socat",      "listeners and tunnels",          "system"),
    ("nmap",       "network recon",                  "fetch-pkg.sh nmap"),
    ("binwalk",    "firmware / embedded archives",   "fetch-pkg.sh binwalk"),
    ("exiftool",   "image and document metadata",    "fetch-pkg.sh perl-image-exiftool"),
    ("ffuf",       "content discovery",              "go install github.com/ffuf/ffuf/v2@latest"),
    ("sqlmap",     "SQL injection",                  "system"),
    ("tcpdump",    "capture",                        "fetch-pkg.sh tcpdump"),
    ("tshark",     "pcap dissection",                "fetch-pkg.sh wireshark-cli"),
    ("zsteg",      "PNG/BMP stego",                  "gem install zsteg"),
    ("steghide",   "JPEG/audio stego",               "fetch-pkg.sh steghide (AUR)"),
    ("stegseek",   "fast steghide cracker",          "fetch-pkg.sh stegseek (AUR)"),
    ("pngcheck",   "PNG chunk integrity",            "fetch-pkg.sh pngcheck (AUR)"),
    ("john",       "hash cracking",                  "fetch-pkg.sh john"),
    ("hashcat",    "GPU hash cracking",              "fetch-pkg.sh hashcat"),
    ("rizin",      "disassembly / reversing",        "https://rizin.re"),
    ("ghidra",     "decompiler",                     "https://ghidra-sre.org"),
    ("upx",        "unpacking",                      "fetch-pkg.sh upx"),
    ("photorec",   "file carving",                   "fetch-pkg.sh testdisk"),
    ("fls",        "Sleuth Kit - filesystem",        "fetch-pkg.sh sleuthkit"),
    ("vol",        "Volatility 3 - memory",          "uv pip install volatility3"),
    ("nc",         "netcat - shells",                "fetch-pkg.sh openbsd-netcat"),
    ("subfinder",  "passive subdomain enum",         "go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"),
    ("dnsx",       "bulk DNS resolution",            "go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest"),
    ("whois",      "registration lookup",            "fetch-pkg.sh whois"),
    ("ruby",       "gem-based stego tools",          "fetch-pkg.sh ruby"),
]

# Python modules, checked inside the dedicated CTF venv when it exists.
PY_MODULES = [
    ("pwn",         "pwntools - exploit dev"),
    ("Crypto",      "pycryptodome - ciphers"),
    ("z3",          "z3-solver - constraint solving"),
    ("gmpy2",       "fast big-int maths"),
    ("PIL",         "Pillow - image manipulation"),
    ("numpy",       "arrays / signal work"),
    ("scapy",       "packet crafting"),
    ("capstone",    "disassembly"),
    ("elftools",    "ELF parsing"),
    ("sympy",       "symbolic maths"),
    ("volatility3", "memory forensics"),
    ("ropgadget",   "ROP gadget search"),
    ("hashpumpy",   "hash length extension"),
    ("oletools",    "Office document analysis"),
    ("dns",         "dnspython - DNS recon (no dig on this box)"),
    ("whois",       "registration and history"),
    ("exifread",    "image metadata"),
    ("piexif",      "EXIF write/rewrite"),
    ("phonenumbers","phone number OSINT"),
    ("cv2",         "OpenCV - image analysis"),
    ("stegano",     "LSB steganography"),
    ("lxml",        "XML/XXE and HTML parsing"),
    ("bs4",         "BeautifulSoup - HTML parsing"),
    ("jwt",         "PyJWT - JWT forging"),
    ("flask",       "local test servers"),
    ("websocket",   "WebSocket clients"),
    # Added 2026-09-27: these two were documented in the skills (symbolic-execution-tools,
    # vm-and-bytecode-reverse) and used in real POCTF reverses, but were absent from the venv
    # while this check still printed "26/26 ... READY". A readiness check that omits a
    # documented capability reports a false clean, so they are now verified like the rest.
    ("angr",        "symbolic execution - angr"),
    ("unicorn",     "CPU emulation (custom-VM bytecode)"),
]

VENV = os.path.expanduser("~/.ctf/venv")
VENV_PY = os.path.join(VENV, "bin", "python")

# Some tools ship under several names; any one satisfies the check. Ruby gems
# land in a directory that is not on PATH by default, so the venv bin is used
# as a stowage point for those (symlinked) rather than editing the user's shell.
ALIASES = {
    "nc":       ("nc", "ncat", "netcat", "netcat-openbsd"),
    "vol":      ("vol", "volatility", "vol.py"),
    "photorec": ("photorec", "testdisk"),
}


def have(cmd: str) -> bool:
    """On PATH, or provided by the dedicated CTF venv.

    The venv's bin/ is deliberately not on PATH, so a bare shutil.which() would
    report tools we installed ourselves as missing - which is worse than not
    checking at all, because it sends you reinstalling what you already have.
    """
    for name in ALIASES.get(cmd, (cmd,)):
        if shutil.which(name) is not None:
            return True
        if os.path.exists(os.path.join(VENV, "bin", name)):
            return True
    return False


def venv_modules() -> set[str]:
    """Ask the venv itself which modules import, rather than guessing."""
    if not os.path.exists(VENV_PY):
        return set()
    probe = ("import importlib.util as u, json, sys;"
             "print(json.dumps([m for m in sys.argv[1:] if u.find_spec(m)]))")
    names = [m for m, _ in PY_MODULES]
    try:
        out = subprocess.run([VENV_PY, "-c", probe, *names],
                             capture_output=True, text=True, timeout=120)
        import json
        return set(json.loads(out.stdout.strip() or "[]"))
    except Exception:
        return set()


# The write-up is a SCORED deliverable on most finals boards, and it is built
# with a headless browser over CDP. Losing the browser at hour ten means losing
# the report, so its prerequisites belong in the same preflight as the exploits.
WRITEUP_CLI = [
    ("node",       "markdown -> HTML -> PDF renderer", "system"),
    ("pdfinfo",    "page/size verification before submit", "poppler"),
    ("pdfimages",  "proves every proof image embedded",    "poppler"),
]
CDP_URL = "http://127.0.0.1:9222/json/version"
CDP_FIX = ("nohup chromium --headless=new --remote-debugging-port=9222 "
           "--user-data-dir=$HOME/.ctf-profile >/tmp/chrome.log 2>&1 &")


def cdp_up(timeout: float = 3.0) -> bool:
    """True when a CDP browser is actually answering, not merely port-open."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(CDP_URL, timeout=timeout) as r:
            return bool(json.loads(r.read().decode("utf-8", "replace")).get("Browser"))
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Report CTF toolchain readiness.")
    ap.add_argument("--quiet", action="store_true", help="only show problems")
    args = ap.parse_args()

    cli_have = [n for n, _, _ in CLI if have(n)]
    cli_miss = [(n, why, fix) for n, why, fix in CLI if not have(n)]

    mod_have = venv_modules()
    mod_miss = [(m, why) for m, why in PY_MODULES if m not in mod_have]

    wu_miss = [(n, why, fix) for n, why, fix in WRITEUP_CLI if not have(n)]
    cdp = cdp_up()

    if not args.quiet:
        print("=" * 72)
        print("CTF PREFLIGHT")
        print("=" * 72)
        print("\nCLI tools present (%d/%d): %s"
              % (len(cli_have), len(CLI), ", ".join(cli_have)))
        print("\nPython venv: %s%s"
              % (VENV, "" if os.path.exists(VENV_PY) else "   <-- MISSING"))
        print("Python modules present (%d/%d): %s"
              % (len(mod_have), len(PY_MODULES), ", ".join(sorted(mod_have))))

        print("\nWrite-up pipeline (the report is a scored deliverable):")
        print("  node/pdfinfo/pdfimages : %s"
              % ("all present" if not wu_miss
                 else "MISSING " + ", ".join(n for n, _, _ in wu_miss)))
        print("  CDP browser :9222      : %s"
              % ("reachable" if cdp else "NOT RUNNING - cannot render the PDF"))

    if cli_miss:
        print("\nMISSING CLI TOOLS")
        print("  No apt here, and sudo needs a password. `pacman -Sp` resolves a\n  package and its dependencies WITHOUT root, and an Arch package is just a\n  zstd tarball, so these run out of a user directory - no install, nothing to\n  uninstall, no system change before an event:  bash ~/.ctf/fetch-pkg.sh <pkg>")
        for n, why, fix in cli_miss:
            print("  %-11s %-34s fix: %s" % (n, why, fix))
    if mod_miss:
        print("\nMISSING PYTHON MODULES")
        for m, why in mod_miss:
            print("  %-12s %s" % (m, why))
        print("\n  fix:  uv pip install --python %s %s"
              % (VENV_PY, " ".join({"Crypto": "pycryptodome", "z3": "z3-solver",
                                    "PIL": "pillow", "elftools": "pyelftools",
                                    "pwn": "pwntools"}.get(m, m) for m, _ in mod_miss)))

    if wu_miss or not cdp:
        print("\nWRITE-UP PIPELINE GAPS")
        for n, why, fix in wu_miss:
            print("  %-11s %-34s fix: %s" % (n, why, fix))
        if not cdp:
            print("  %-11s %-34s fix: %s" % (
                "chromium", "headless browser for the PDF", CDP_FIX))
        print("  (the report is judged; fix this BEFORE the deadline, not after)")

    # Only these stop work outright; the rest degrade a category.
    critical = ("python3", "file", "strings", "readelf", "openssl", "curl")
    crit_missing = [n for n in critical if not have(n)]
    if crit_missing:
        print("\nCRITICAL MISSING: %s" % ", ".join(crit_missing))
        return 1
    if not args.quiet:
        print("\nREADY. Use the venv for Python tooling:")
        print("  %s your_solve.py" % VENV_PY)
        print("  or: source %s/bin/activate" % VENV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
