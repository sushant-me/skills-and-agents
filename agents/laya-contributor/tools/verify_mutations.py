#!/usr/bin/env python3
"""Verify the mutation claims the PR bodies make — "disable this guard and exactly these tests fail".

WHY THIS EXISTS
---------------
Six of the prepared PR bodies state a mutation result, and it is the strongest claim any of
them makes: not "I added tests", but "the tests fail when the fix is removed". A maintainer
who tries the experiment and gets a different number learns the author did not run it. Until
now nothing checked these, which is the same gap as every other count in this workspace — a
number in a sentence that no run derives.

Each claim is a row in MUTATIONS: the branch, a precise edit that disables the fix, the test
target, and what the body says should happen. The tool checks out the branch into a
throwaway worktree (never the clone), applies the edit, runs the test target with the
isolated environment, and compares the observed failure set with the claim.

    python3 verify_mutations.py                 # every claim
    python3 verify_mutations.py --only omni     # substring filter
    python3 verify_mutations.py --self-test     # the comparators, without running anything

ENVIRONMENT
-----------
Same discipline as measure_prepared_counts: scratch HOME plus an in-memory keyring, because
the Laya engine suite rewrites ~/.laya/settings.json and its teardown deletes the real MCP
token from the OS keychain (measured: 34 passing tests, token gone).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path.home() / "Work"
_SCRATCH_HOME = pathlib.Path(
    os.environ.get("LAYA_MUTATION_HOME", f"/tmp/laya-mutation-home-{os.getuid()}"
                   if hasattr(os, "getuid") else "/tmp/laya-mutation-home"))

FAILED_NODEID = re.compile(r"^FAILED\s+(\S+?)(?:\s+-\s|$)", re.M)
SUMMARY = re.compile(r"(\d+) failed")


class Claim:
    """One mutation claim: disable the fix this way, and exactly this should break."""

    def __init__(self, key: str, branch: str, clone: str, path: str, old: str, new: str,
                 target: list[str], expect_failed: int, expect_names: tuple[str, ...] = (),
                 note: str = "", whole_file: bool = False):
        self.key = key
        self.branch = branch
        self.clone = clone
        self.path = path
        self.old = old
        self.new = new
        self.target = target
        self.expect_failed = expect_failed
        self.expect_names = expect_names
        self.note = note
        self.whole_file = whole_file


# Each entry quotes the claim from the PR body and names the body in `note`, so a mismatch
# can be traced to the sentence that has to change.
MUTATIONS: tuple[Claim, ...] = (
    Claim(
        "cross-site: http middleware neutralised",
        "fix/engine-cross-site-origin-guard", "laya-inspect", "engine/laya/main.py",
        "    if not origin_is_allowed(origin):\n        log.warning(\"cross_site_request_blocked\"",
        "    if False:\n        log.warning(\"cross_site_request_blocked\"",
        ["engine/tests/test_origin_guard.py"], 2,
        ("test_",),
        note="PR: 'HTTP middleware neutralised -> fails exactly the two cross-site HTTP tests'",
    ),
    Claim(
        "cross-site: websocket handshake check removed",
        "fix/engine-cross-site-origin-guard", "laya-inspect", "engine/laya/main.py",
        "    origin = websocket.headers.get(\"origin\")\n"
        "    if not origin_is_allowed(origin):",
        "    origin = websocket.headers.get(\"origin\")\n    if False:",
        ["engine/tests/test_origin_guard.py"], 1,
        (),
        note="PR: 'WebSocket handshake check removed -> fails exactly the WebSocket refusal "
             "test'",
    ),
    Claim(
        "attention-wipe: guard disabled (wiped = 0)",
        "fix/omni-attention-wipe-guard", "laya-inspect", "engine/laya/pipeline/omni.py",
        "    wiped = _attention_wipe_count(guard_baseline, result_sections, out_meta)",
        "    wiped = 0",
        ["engine/tests/test_omni_resynthesis.py"], 1,
        ("test_wiping_attention_with_a_live_item_is_not_stored",),
        note="PR: 'guard disabled (`wiped = 0`) -> fails exactly "
             "test_wiping_attention_with_a_live_item_is_not_stored'",
    ),
    Claim(
        "attention-wipe: narrowing reverted to any carried item",
        "fix/omni-attention-wipe-guard", "laya-inspect", "engine/laya/pipeline/omni.py",
        '''            if _subject_survives(item, result_sections):
                continue  # moved (R3/R4) or regrouped (R2) — not dropped
            priority = _open_max_priority(_item_source_cards(item), meta)
            if priority in _ATTENTION_PRIORITIES:
                dropped += 1''',
        "            dropped += 1",
        ["engine/tests/test_omni_resynthesis.py"], 6,
        (),
        note="PR (corrected): 'narrowing reverted to any non-terminal carried item -> fails "
             "exactly the six tests that depend on it'; published as 3 until this ran",
    ),
    Claim(
        "attention-wipe: guard_baseline reverted to prior_sections",
        "fix/omni-attention-wipe-guard", "laya-inspect", "engine/laya/pipeline/omni.py",
        "    guard_baseline = prior_sections if current_snapshot is not None else []",
        "    guard_baseline = prior_sections",
        ["engine/tests/test_omni_resynthesis.py"], 1,
        ("test_the_repair_of_a_poisoned_snapshot_is_not_rejected",),
        note="PR: '`guard_baseline` reverted to `prior_sections` -> fails exactly "
             "test_the_repair_of_a_poisoned_snapshot_is_not_rejected'",
    ),
    Claim(
        "unitemised-cards: catch-all sent to attention",
        "fix/omni-unitemised-cards", "laya-inspect", "engine/laya/pipeline/omni.py",
        '''    target = next(
        (s for s in result_sections if s.get("type") == "recent"),
        result_sections[-1] if result_sections else None,
    )''',
        '''    target = next(
        (s for s in result_sections if s.get("type") == "attention"),
        result_sections[-1] if result_sections else None,
    )''',
        ["engine/tests/test_omni_resynthesis.py"], 2,
        (),
        note="PR: 'the catch-all goes to `attention` -> fails the attention test (and the "
             "pre-existing empty-result-guard test)'; the index says 1 — one of the two is "
             "wrong",
    ),
    Claim(
        "unitemised-cards: call moved below the change summary",
        "fix/omni-unitemised-cards", "laya-inspect", "engine/laya/pipeline/omni.py",
        '''    kept_dropped = _add_catch_all_for_unrepresented(new_cards, result_sections, space_id)
    change_summary = compute_resynthesis_change_summary(
        prior_sections,
        result_sections,
        out_meta,
        _TERMINAL_STATUSES,
        resolved_at_by_entity,
    )''',
        '''    change_summary = compute_resynthesis_change_summary(
        prior_sections,
        result_sections,
        out_meta,
        _TERMINAL_STATUSES,
        resolved_at_by_entity,
    )
    kept_dropped = _add_catch_all_for_unrepresented(new_cards, result_sections, space_id)''',
        ["engine/tests/test_omni_resynthesis.py"], 2,
        (),
        note="PR: 'the call moved below the change summary -> fails exactly the announcement "
             "and key tests'",
    ),
    Claim(
        "unitemised-cards: no catch-all",
        "fix/omni-unitemised-cards", "laya-inspect", "engine/laya/pipeline/omni.py",
        "    kept_dropped = _add_catch_all_for_unrepresented(new_cards, result_sections, space_id)",
        "    kept_dropped = 0",
        ["engine/tests/test_omni_resynthesis.py"], 4,
        (),
        note="PR (corrected): 'no catch-all -> fails all four tests in "
             "TestUnitemisedCardsAreNotLost'; published as 3 until this ran",
    ),
)


def suite_env() -> dict:
    pythonpath = [str(HERE)]
    if os.environ.get("PYTHONPATH"):
        pythonpath.append(os.environ["PYTHONPATH"])
    return {
        "HOME": str(_SCRATCH_HOME),
        "USERPROFILE": str(_SCRATCH_HOME),
        "PYTHONPATH": os.pathsep.join(pythonpath),
        "PYTHON_KEYRING_BACKEND": "memkeyring.InMemoryKeyring",
    }


def git(clone: pathlib.Path, *args: str, check: bool = True) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out}")
    return proc.returncode, out


def parse_failures(output: str) -> list[str]:
    """The nodeids pytest reported as FAILED, deduplicated and sorted.

    pytest prints a `FAILED <nodeid>` line per failure in its short summary; using that
    rather than the pass/fail counts is what makes "exactly these tests" checkable.
    """
    names = []
    for nodeid in FAILED_NODEID.findall(output):
        if nodeid not in names:
            names.append(nodeid)
    return sorted(names)


def run_claim(claim: Claim, timeout: int = 900) -> dict:
    """Apply one mutation in a throwaway worktree and observe what fails. Never raises."""
    record: dict = {"key": claim.key, "branch": claim.branch, "expected": claim.expect_failed,
                    "note": claim.note}
    clone = WORK / claim.clone
    if not (clone / ".git").exists():
        record["error"] = f"{clone} is not a clone"
        return record
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mutation-wt-"))
    where = scratch / claim.clone
    try:
        _, sha = git(clone, "rev-parse", claim.branch)
        record["sha"] = (sha or "")[:12]
        git(clone, "worktree", "add", "--detach", str(where), claim.branch)
        venv = clone / "engine" / ".venv"
        link = where / "engine" / ".venv"
        if venv.exists() and not link.exists():
            link.symlink_to(venv)
        target = where / claim.path
        text = target.read_text(encoding="utf-8")
        if text.count(claim.old) != 1:
            record["error"] = (f"the mutation anchor appears {text.count(claim.old)} times in "
                               f"{claim.path} — the branch moved; update the claim")
            return record
        target.write_text(text.replace(claim.old, claim.new), encoding="utf-8")
        python = (where / "engine" / ".venv" / "bin" / "python")
        # The table names test targets repo-relative (`engine/tests/...`) because that is
        # how a reader finds them, but pytest runs with cwd=`engine`, so the prefix has to
        # come off. The first run passed the prefixed path and pytest exited 4 (usage
        # error) in half a second — reported honestly as a mismatch rather than as a quiet
        # pass, which is how it was noticed at all.
        targets = [t[len("engine/"):] if t.startswith("engine/") else t
                   for t in claim.target]
        started = time.time()
        proc = subprocess.run([str(python), "-m", "pytest", "-q", *targets],
                              cwd=str(where / "engine"), capture_output=True, text=True,
                              timeout=timeout, env={**os.environ, **suite_env()})
        output = proc.stdout + proc.stderr
        record["failed"] = parse_failures(output)
        record["exit"] = proc.returncode
        record["wall"] = f"{time.time() - started:.1f}s"
        summary = SUMMARY.search(output)
        record["summary"] = summary.group(0) if summary else "no 'N failed' line"
        if proc.returncode == 0:
            record["error"] = ("the mutation did not fail anything — the tests do not cover "
                               "the guard this claim is about")
        elif proc.returncode in (2, 3, 4):
            # 2 = interrupted/collection error, 3 = internal error, 4 = usage error. None of
            # these is a test failure, and reading one as "0 tests failed" would let a broken
            # run masquerade as a claim that could not be reproduced.
            record["error"] = (f"pytest exited {proc.returncode} ({record['summary']}) — the "
                               f"run did not complete: {output.strip().splitlines()[-1][:120]}")
    except subprocess.TimeoutExpired:
        record["error"] = f"timed out after {timeout}s"
    except Exception as exc:                                     # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        git(clone, "worktree", "remove", "--force", str(where), check=False)
        git(clone, "worktree", "prune", check=False)
        shutil.rmtree(scratch, ignore_errors=True)
    return record


def judge(record: dict) -> tuple[bool, str]:
    """Did the observed failure set match the claim?"""
    if "error" in record:
        return False, record["error"]
    failed = record.get("failed") or []
    if len(failed) != record["expected"]:
        return False, (f"the body claims exactly {record['expected']} test(s) fail; "
                       f"{len(failed)} did ({record['summary']})")
    for needle in record.get("expect_names", ()):  # kept for future claims
        if not any(needle in nodeid for nodeid in failed):
            return False, f"the claim names a test containing {needle!r}; none failed"
    return True, f"{len(failed)} failed, as claimed: " + ", ".join(
        nodeid.rsplit("::", 1)[-1] for nodeid in failed)


def self_test() -> int:
    """The comparators, which is where a false result would come from."""
    failures = 0
    sample = ("tests/test_a.py::test_one\n"
              "FAILED tests/test_x.py::test_y - AssertionError: boom\n"
              "FAILED tests/test_x.py::test_z - AssertionError: boom\n"
              "1 failed, 3 passed in 1.00s\n")
    got = parse_failures(sample)
    if got != ["tests/test_x.py::test_y", "tests/test_x.py::test_z"]:
        print(f"  FAILED: parse_failures returned {got}")
        failures += 1
    ok, why = judge({"expected": 2, "failed": got, "summary": "2 failed"})
    if not ok:
        print(f"  FAILED: a matching count was rejected ({why})")
        failures += 1
    ok, why = judge({"expected": 1, "failed": got, "summary": "2 failed"})
    if ok:
        print("  FAILED: a count mismatch was accepted")
        failures += 1
    ok, why = judge({"expected": 2, "failed": [], "empty": True,
                     "error": "the mutation did not fail anything"})
    if ok:
        print("  FAILED: a mutation that broke nothing was accepted")
        failures += 1
    # "exactly these tests" is only checkable against the real nodeids, so the tool must
    # never fall back to a pass/fail count when the nodeid lines are absent.
    if parse_failures("1 failed, 3 passed in 1.00s"):
        print("  FAILED: a summary line without nodeids produced names")
        failures += 1
    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", default=[],
                        help="substring filter on the claim key (repeatable)")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    _SCRATCH_HOME.mkdir(parents=True, exist_ok=True)
    try:
        _SCRATCH_HOME.chmod(0o700)
    except OSError:
        pass

    claims = [c for c in MUTATIONS
              if not args.only or any(f in c.key for f in args.only)]
    if not claims:
        print(f"no claims matched {args.only}", file=sys.stderr)
        return 2

    print(f"verifying {len(claims)} mutation claim(s) from the PR bodies\n")
    bad = 0
    for index, claim in enumerate(claims, 1):
        print(f"[{index}/{len(claims)}] {claim.key}")
        print(f"      {claim.note}")
        record = run_claim(claim, timeout=args.timeout)
        ok, why = judge(record)
        if ok:
            print(f"      ok — {why}")
        else:
            bad += 1
            print(f"      MISMATCH — {why}")
        print()
    if bad:
        print(f"{bad} of {len(claims)} claim(s) do not match what was measured — fix the "
              f"body, or the test it is about")
        return 1
    print(f"all {len(claims)} mutation claim(s) match what was measured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
