#!/usr/bin/env python3
"""Refuse to let you run Laya's test suite in a tree that would eat your token.

Why this exists
---------------
`engine/tests/test_mcp_http.py::restore_settings` calls `save_settings()` and
`delete_mcp_token()`, and `config.py` resolves `LAYA_HOME` from `Path.home()` at
*import* time. So on a tree without the isolation fix, a plain `pytest` rewrites
the developer's real `~/.laya/settings.json` and deletes the MCP bearer token from
the OS keychain. It reads as "my token stopped working".

That happened twice on this machine. The first time, the fix did not exist yet.
The second time it did -- on another branch -- and the rule was written down in
prose and ignored anyway. A rule that has to be remembered is not a control.

What it does
------------
Three states, and it does not guess:

  SAFE     the tree redirects HOME before importing laya, or HOME is already
           pointed somewhere that is not the real one.
  UNSAFE   neither, and running pytest here will delete the real token.
  UNKNOWN  it cannot tell, and says so rather than reporting a pass.

    python3 tools/check_laya_home.py            # check the current tree
    python3 tools/check_laya_home.py --repo DIR # check another checkout
    HOME=/tmp/scratch python3 tools/check_laya_home.py

Run this before `pytest` on any Laya tree that is not yours to damage.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

# The markers the isolation fix leaves in conftest.py. The redirect has to happen
# before the first `laya` import, so its absence is the thing that matters, not
# the presence of a comment.
REDIRECT_MARKERS = (
    'os.environ["HOME"] = _TEST_HOME',
    'os.environ["USERPROFILE"] = _TEST_HOME',
)

SAFE = "SAFE"
UNSAFE = "UNSAFE"
UNKNOWN = "UNKNOWN"


def real_home() -> pathlib.Path:
    """The real home, with the same $HOME override removed.

    `Path.home()` reads the current process's HOME, which is exactly what we are
    trying to test, so it cannot be used to find the thing we are comparing
    against.
    """
    return pathlib.Path(os.environ.get("LAYA_REAL_HOME") or
                        pathlib.Path(os.path.expanduser("~")).anchor or "/home") / ""


def classify(repo: pathlib.Path) -> tuple[str, str]:
    conftest = repo / "engine" / "tests" / "conftest.py"
    if not conftest.exists():
        return UNKNOWN, f"no {conftest} — is this a Laya checkout?"

    text = conftest.read_text(encoding="utf-8", errors="replace")
    missing = [m for m in REDIRECT_MARKERS if m not in text]
    if not missing:
        return SAFE, "conftest.py redirects HOME before importing laya"

    # No redirect in the tree. The suite is still safe if THIS process's HOME is
    # already somewhere harmless, because the tests inherit it.
    home = os.environ.get("HOME", "")
    laya_dir = pathlib.Path(home) / ".laya" if home else None
    if home and os.environ.get("LAYA_HOME_IS_SCRATCH") == "1":
        return SAFE, f"HOME is {home}, explicitly marked as a scratch directory"
    if home and laya_dir is not None and not laya_dir.exists():
        return UNKNOWN, (
            f"no redirect in the tree, but HOME={home} has no .laya yet. "
            "Running the suite would create one there rather than touching your "
            "real config — but set LAYA_HOME_IS_SCRATCH=1 to make that explicit")

    return UNSAFE, (
        "conftest.py does NOT redirect HOME, and HOME is not a marked scratch "
        "directory. Running `pytest` here rewrites the real ~/.laya/settings.json "
        "and deletes the MCP bearer token from the keychain.")


def self_test() -> int:
    """Prove all three verdicts are reachable, so none is hard-coded.

    A guard that always answers the same thing is not a guard. Each state is
    exercised against a synthetic tree, including the one that matters: an
    unmarked HOME that already holds a `.laya` must be UNSAFE, not UNKNOWN.
    """
    import tempfile

    failures = 0
    print("self-test: every verdict is reachable")
    saved = {k: os.environ.get(k) for k in ("HOME", "LAYA_HOME_IS_SCRATCH")}

    def case(conftest: str | None, home: str, scratch: bool,
             expect: str, description: str) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp)
            (repo / "engine" / "tests").mkdir(parents=True)
            if conftest is not None:
                (repo / "engine" / "tests" / "conftest.py").write_text(
                    conftest, encoding="utf-8")
            os.environ["HOME"] = home
            if scratch:
                os.environ["LAYA_HOME_IS_SCRATCH"] = "1"
            else:
                os.environ.pop("LAYA_HOME_IS_SCRATCH", None)
            verdict, why = classify(repo)
        if verdict != expect:
            print(f"  FAILED: {description}\n    expected {expect}, got {verdict} — {why}")
            failures += 1
        else:
            print(f"  ok: {description}")

    redirecting = ('os.environ["HOME"] = _TEST_HOME\n'
                   'os.environ["USERPROFILE"] = _TEST_HOME\n')
    try:
        case(None, "/home/someone", False, UNKNOWN,
             "a tree with no conftest.py is UNKNOWN")
        case(redirecting, "/home/someone", False, SAFE,
             "a conftest.py that redirects HOME is SAFE")
        with tempfile.TemporaryDirectory() as home:
            (pathlib.Path(home) / ".laya").mkdir()
            case("nothing here\n", home, False, UNSAFE,
                 "an unmarked HOME that already has .laya is UNSAFE")
            case("nothing here\n", home, True, SAFE,
                 "a marked scratch HOME is SAFE despite no redirect")
            case("nothing here\n", str(pathlib.Path(home) / "empty"), False, UNKNOWN,
                 "an unmarked HOME with no .laya is UNKNOWN, not SAFE")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".",
                        help="a Laya checkout (default: the current directory)")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the SAFE/UNSAFE/UNKNOWN verdicts are reachable")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    repo = pathlib.Path(args.repo).resolve()
    verdict, why = classify(repo)

    print(f"{verdict}: {repo}")
    print(f"  {why}")

    if verdict == UNSAFE:
        print()
        print("  Fix one of these ways:")
        print("    - use the branch carrying the isolation fix:")
        print("        git checkout fix/tests-isolate-laya-home")
        print("    - or run the suite against a scratch HOME:")
        print("        HOME=$(mktemp -d) LAYA_HOME_IS_SCRATCH=1 pytest engine/tests -q")
        print("    - note: a FIXED scratch directory caches ChromaDB's model; a")
        print("      fresh mktemp each run re-downloads it (43s -> 241s).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
