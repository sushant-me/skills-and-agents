#!/usr/bin/env python3
"""Measure the prepared branches' suite counts, so a quoted number has a provenance.

WHY THIS EXISTS
---------------
Every PR body quotes numbers — "1081 passed", "248 passed", "277 passed". Those are
the figures a maintainer weighs when deciding whether to trust a patch, and until
now **nothing checked any of them**. Three real defects came from exactly that gap:

  * a body quoted `1093 passed` for a concurrency experiment that had been run on a
    *different* branch, printed next to its own `1081` with nothing saying so;
  * a body claimed "Six unit tests" where the branch added seven;
  * the user's own reputation repo published `58 tests` for a suite that collects 60.

A number that nothing derives is a number that drifts silently. This tool derives
them: it runs each prepared branch's suite and records what the run actually
printed, with the command, the commit and the raw summary line as provenance.
`check_pr_bodies.py --require-counts` then fails a body that quotes a figure no
measurement supports, or quotes another branch's figure without naming that branch.

WHAT IT DOES NOT DO
-------------------
It never invents a figure. A run that fails, times out or prints no summary is
recorded as `error` with the raw tail — an unmeasured branch stays visibly
unmeasured rather than acquiring a plausible number.

HOW IT RUNS A BRANCH WITHOUT TOUCHING THE CLONE
-----------------------------------------------
`git worktree add --detach`, never a checkout: the clone is left on whatever branch
the developer left it on, and the reviewers' notes about restoring state by hand stop
applying. `engine/.venv` and `ui/node_modules` are gitignored, so they are symlinked
from the clone into the worktree — the engine suite imports `laya` from the worktree
(there is no editable install to fight) while the interpreter stays the clone's.

SAFETY
------
The engine suite rewrites `~/.laya/settings.json` and, because the OS keychain is not
scoped by HOME, its teardown deletes the developer's real MCP bearer token (measured:
34 passing tests, token gone). Every pytest run here therefore gets a scratch HOME
*and* an in-memory keyring backend. Runs are sequential by construction.

USAGE
-----
    python3 measure_prepared_counts.py                      # engine suite, every branch
    python3 measure_prepared_counts.py --suite ui           # vitest, branches that quote it
    python3 measure_prepared_counts.py --only fix/dev-requirements
    python3 measure_prepared_counts.py --self-test          # parser + refusal tests, no git
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_WORK_DIR = pathlib.Path.home() / "Work"
DEFAULT_MANIFEST = DEFAULT_WORK_DIR / "prepared-counts.json"

# A stable scratch HOME, not a fresh one per run: redirecting HOME also relocates
# ChromaDB's model cache, and a cold cache made the engine suite take 241s instead of 43s.
_SCRATCH_HOME = pathlib.Path(
    os.environ.get("LAYA_COUNTS_HOME", f"/tmp/laya-counts-home-{os.getuid()}"
                   if hasattr(os, "getuid") else "/tmp/laya-counts-home"))

SUITES = {
    # name: (subdir, argv, summary kind)
    "engine": ("engine", ["{PY}", "-m", "pytest", "-q"], "pytest"),
    "ui": ("ui", ["npx", "vitest", "run"], "vitest"),
    "cargo": ("ui/src-tauri", ["cargo", "test", "--lib"], "cargo"),
}

_PYTEST_PASSED = re.compile(r"(\d+) passed")
_VITEST_TESTS = re.compile(r"^[ \t]*Tests[ \t]+(.+)$", re.M)
_VITEST_COUNT = re.compile(r"(\d+)\s+(passed|failed|skipped|todo)")
_CARGO_PASSED = re.compile(r"test result: \w+\. (\d+) passed")
_ANY_FAIL = re.compile(r"(\d+) (?:failed|error|errors)")


def _vitest_figures(output: str) -> dict | None:
    """vitest's `Tests` line, green or mixed.

    The first version only matched `Tests  N passed`, so a *deliberately red* mutation —
    `Tests  2 failed | 244 passed (246)`, which is exactly the evidence that the tests
    are load-bearing — parsed as no figure at all. A parser that can only see green runs
    cannot record the mutation that proves a test matters.
    """
    match = _VITEST_TESTS.search(output)
    if not match:
        return None
    figures: dict[str, int] = {}
    for count, what in _VITEST_COUNT.findall(match.group(1)):
        key = {"passed": "passed", "failed": "not_passed"}.get(what, what)
        figures[key] = figures.get(key, 0) + int(count)
    return figures or None


def parse_summary(kind: str, output: str) -> dict | None:
    """(figures) from a suite's tail, or None when nothing usable was printed.

    Pure, so the self-test can pin the four shapes that actually occur: a clean pytest
    run, a pytest run with failures, vitest's `Tests  N passed (N)`, and cargo's
    `test result: ok. N passed`. Returning None — rather than 0 — is the point: a run
    that printed no summary must not become a measurement of zero.
    """
    if kind == "vitest":
        return _vitest_figures(output)
    if kind == "cargo":
        # Sum every `test result:` line: cargo prints one per test binary.
        found = [int(x) for x in _CARGO_PASSED.findall(output)]
        return {"passed": sum(found)} if found else None
    # pytest: report the last summary line, which is the whole-suite one.
    lines = [ln.strip() for ln in output.splitlines() if _PYTEST_PASSED.search(ln)]
    if not lines:
        return None
    line = lines[-1]
    figures = {"passed": int(_PYTEST_PASSED.search(line).group(1))}
    bad = _ANY_FAIL.search(line)
    if bad:
        figures["not_passed"] = int(bad.group(1))
    return figures


def summary_line(kind: str, output: str) -> str:
    """The line the figure came from — the provenance, so it is the matched line.

    Taking the *last* line instead recorded a Node deprecation warning as the evidence
    for two vitest measurements, which is provenance that proves nothing.
    """
    patterns = {
        "vitest": _VITEST_TESTS,
        "cargo": _CARGO_PASSED,
        "pytest": _PYTEST_PASSED,
    }
    matches = [ln.strip() for ln in output.splitlines()
               if patterns[kind].search(ln) or (kind == "pytest"
                                                and _ANY_FAIL.search(ln))]
    return matches[-1][:200] if matches else ""


def plan_rows(work: pathlib.Path) -> list[tuple[str, str]]:
    """(branch, clone) for every prepared branch, plus each clone's `main` as the base."""
    spec = importlib.util.spec_from_file_location(
        "_spw_for_counts", HERE / "submit_prepared_work.py")
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = [(branch, clone) for branch, clone, _b, _d in module.PLAN]
    for clone in dict.fromkeys(c for _b, c in rows):
        rows.append(("main", clone))
    return rows


def git(clone: pathlib.Path, *args: str, check: bool = True) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(clone), *args],
                          capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out}")
    return proc.returncode, out


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


def prepare_worktree(clone: pathlib.Path, branch: str, where: pathlib.Path) -> None:
    git(clone, "worktree", "add", "--detach", str(where), branch)
    # Gitignored build/test state: symlinked, never copied — a copy of node_modules
    # is hundreds of megabytes and would hide the checkout under test. `.svelte-kit`
    # is here because `ui/tsconfig.json` extends `./.svelte-kit/tsconfig.json`, which
    # SvelteKit generates: without it the UI suite dies inside vite's tsconfig lookup,
    # which is how the first UI attempt failed (both branches, exit 1, no summary).
    for rel in ("engine/.venv", "ui/node_modules", "ui/.svelte-kit"):
        target = clone / rel
        link = where / rel
        if target.exists() and not link.exists():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target)


def drop_worktree(clone: pathlib.Path, where: pathlib.Path) -> None:
    git(clone, "worktree", "remove", "--force", str(where), check=False)
    git(clone, "worktree", "prune", check=False)


def measure_one(clone: pathlib.Path, branch: str, suite: str,
                timeout: int = 1800, variant: str | None = None,
                pre_suite: str | None = None) -> dict:
    """Run one suite on one branch in a throwaway worktree. Never raises.

    `pre_suite` is a shell command run inside the worktree before the suite, and
    `variant` labels the resulting entry. Together they measure a *counterfactual* —
    "the same tree with the two new tests removed is 246" — which two PR bodies assert
    and which is otherwise a number nothing can check. The entry is stored under its
    own key, so a variant measurement can never be mistaken for the branch's own.
    """
    subdir, argv, kind = SUITES[suite]
    record: dict = {"branch": branch, "suite": suite, "clone": clone.name}
    if variant:
        record["variant"] = variant
        record["pre_suite"] = pre_suite
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="counts-wt-"))
    where = scratch / clone.name
    try:
        _, sha = git(clone, "rev-parse", branch)
        record["sha"] = sha.strip().split()[0][:12] if sha else ""
        prepare_worktree(clone, branch, where)
        if pre_suite:
            prep = subprocess.run(pre_suite, shell=True, cwd=str(where),
                                  capture_output=True, text=True, timeout=300)
            if prep.returncode != 0:
                record["error"] = (f"pre-suite command exited {prep.returncode}: "
                                   f"{(prep.stdout + prep.stderr).strip()[:300]}")
                return record
        engine_py = clone / "engine" / ".venv" / "bin" / "python"
        argv = [str(engine_py) if a == "{PY}" else a for a in argv]
        cwd = where / subdir
        started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        proc = subprocess.run(argv, cwd=str(cwd), env={**os.environ, **suite_env()},
                              capture_output=True, text=True, timeout=timeout)
        output = proc.stdout + proc.stderr
        record.update({
            "command": " ".join(argv),
            "cwd": f"<worktree>/{subdir}",
            "exit": proc.returncode,
            "measured_at": started,
            "summary": summary_line(kind, output),
        })
        figures = parse_summary(kind, output)
        if figures is None:
            record["error"] = "the run printed no recognisable summary line"
            record["tail"] = "\n".join(output.strip().splitlines()[-6:])[:800]
        else:
            record["figures"] = figures
            # A figure is only a *measurement* when the branch is green; a red run's
            # "N passed" is a number no one should quote as evidence.
            record["green"] = proc.returncode == 0 and "not_passed" not in figures
    except subprocess.TimeoutExpired:
        record["error"] = f"timed out after {timeout}s"
    except Exception as exc:                                    # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        drop_worktree(clone, where)
        shutil.rmtree(scratch, ignore_errors=True)
    return record


def load_manifest(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {"entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"entries": {}}
    if not isinstance(data.get("entries"), dict):
        data["entries"] = {}
    migrate_legacy_keys(data, path)
    return data


def migrate_legacy_keys(manifest: dict, path: pathlib.Path) -> list[str]:
    """Re-key entries written before the key gained a clone prefix; newest per subject wins.

    This exists because the key format changed mid-run and nothing migrated the old rows.
    `main|engine` (1074, measured when main was `c39c79f`) sat beside the new
    `laya-inspect|main|engine` (1134, on `e87be4`), and BOTH were read — so a superseded
    figure went on answering for "the base tree's count" and the check that compares the PR
    bodies against measurements was quietly satisfied by a number that described a base two
    commits old. A measurement is a claim about a commit; when the commit moves, the claim
    does not silently transfer.

    The record carries its own clone, so the fix is mechanical: fold legacy keys into the
    qualified form and keep the most recent measurement of each subject. Reported, never
    silent — a re-key that dropped a differing figure is exactly the kind of thing that
    should be visible.
    """
    entries = manifest.get("entries") or {}
    notes: list[str] = []
    for key in list(entries):
        if key.count("|") >= 2:
            continue                      # already clone-qualified
        record = entries[key]
        if not isinstance(record, dict) or not record.get("clone"):
            continue                      # nothing to re-key it with; leave it visible
        branch, _, suite = key.partition("|")
        new_key = f"{record['clone']}|{branch}|{suite}"
        if record.get("variant"):
            new_key += f"@{record['variant']}"
        existing = entries.get(new_key)
        # `main` moves, so two measurements of it are two facts about two commits — not a
        # duplicate to resolve. The first version of this dropped the older one, which made
        # a PR body that correctly cites "main (c39c79f) measured 1074" look like it was
        # quoting a sibling branch. Keep both, committing the older one in its key.
        if existing is not None and (existing.get("sha") or "") != (record.get("sha") or ""):
            old_sha = (record.get("sha") or "unknown")[:8]
            older_key = f"{new_key}@{old_sha}"
            if entries.get(older_key) is None:
                entries[older_key] = record
                notes.append(f"kept {key} as {older_key} — a different commit has a "
                             f"different count")
            del entries[key]
            continue
        if existing is None:
            entries[new_key] = record
            notes.append(f"re-keyed {key} -> {new_key}")
        elif (record.get("measured_at") or "") > (existing.get("measured_at") or ""):
            entries[new_key] = record
            notes.append(f"re-keyed {key} -> {new_key}, replacing an older measurement")
        else:
            notes.append(f"dropped legacy duplicate {key} "
                         f"({(record.get('figures') or {}).get('passed')}) in favour of "
                         f"{new_key} ({(existing.get('figures') or {}).get('passed')})")
        del entries[key]
    if notes:
        manifest["migrated"] = notes
    return notes


def store(manifest: dict, record: dict) -> None:
    # Keyed by clone as well as branch: `main` exists in both clones, and keying on the
    # branch alone made the second clone's base measurement overwrite the first's. A
    # variant gets its own key so it can never stand in for the branch's own figure.
    key = f"{record['clone']}|{record['branch']}|{record['suite']}"
    if record.get("variant"):
        key += f"@{record['variant']}"
    manifest.setdefault("entries", {})[key] = record


def self_test_measurement() -> list[str]:
    """Exercise `measure_one` itself on a throwaway repository.

    The sweep that found this: replacing `if figures is None:` with `if False:`, forcing
    `record["green"] = True`, and making the pre-suite failure non-fatal each left the
    self-test green, because it only tested `parse_summary` — the parser — and the ghost
    clone, which fails before any of those branches. A measurement tool whose tests never
    take a measurement is evidence about its regexes, not about its numbers.

    The suite is monkeypatched to a trivial command so this costs milliseconds: the
    interpreter, the worktree, the pre-suite and the recording path are all real.
    """
    import subprocess as _subprocess
    import tempfile as _tempfile

    print("self-test: a measurement is taken, and refused when it cannot be")
    failures: list[str] = []
    saved = dict(SUITES)
    try:
        with _tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "repo"
            (repo / "engine").mkdir(parents=True)
            def g(*args: str) -> None:
                _subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e",
                                 "-c", "user.name=t", *args], capture_output=True)
            g("init", "-q", "-b", "main")
            (repo / "engine" / "f.txt").write_text("base\n")
            g("add", "-A"); g("commit", "-q", "-m", "base")
            g("checkout", "-q", "-b", "topic")
            (repo / "engine" / "f.txt").write_text("base\ntopic\n")
            g("add", "-A"); g("commit", "-q", "-m", "topic")

            # A green suite that prints a figure.
            SUITES["probe"] = ("engine", [sys.executable, "-c",
                                          "print('3 passed in 0.01s')"], "pytest")
            record = measure_one(repo, "topic", "probe")
            if record.get("figures") != {"passed": 3} or record.get("green") is not True:
                failures.append(f"a green run was not recorded as one: {record}")
            else:
                print("  ok: a green run records its figure, its commit and green=True")

            # A failing suite still prints "N passed" — that figure must not be quotable.
            SUITES["probe"] = ("engine", [sys.executable, "-c",
                                          "import sys; print('1 failed, 3 passed'); sys.exit(1)"],
                               "pytest")
            record = measure_one(repo, "topic", "probe")
            if record.get("green") is not False:
                failures.append(f"a red run was recorded as green: {record}")
            else:
                print("  ok: a red run is recorded but not as a measurement")

            # A run that prints nothing usable gets an error, never a figure.
            SUITES["probe"] = ("engine", [sys.executable, "-c", "print('no summary here')"],
                               "pytest")
            record = measure_one(repo, "topic", "probe")
            if "figures" in record or "error" not in record:
                failures.append(f"a figureless run produced figures: {record}")
            else:
                print("  ok: a run with no summary line records an error, not a figure")

            # A pre-suite command that fails must stop before the suite runs.
            SUITES["probe"] = ("engine", [sys.executable, "-c",
                                          "print('3 passed in 0.01s')"], "pytest")
            record = measure_one(repo, "topic", "probe", variant="probe",
                                 pre_suite="exit 7")
            if "figures" in record or "pre-suite" not in str(record.get("error")):
                failures.append(f"a failing pre-suite did not stop the measurement: {record}")
            else:
                print("  ok: a failing pre-suite stops the run and says why")
    finally:
        SUITES.clear()
        SUITES.update(saved)
    return failures


def self_test() -> int:
    failures = []
    cases = [
        ("pytest clean", "pytest", "1081 passed in 43.21s", {"passed": 1081}),
        ("pytest red", "pytest", "1 failed, 1080 passed in 60.10s",
         {"passed": 1080, "not_passed": 1}),
        ("vitest", "vitest", " Test Files  19 passed (19)\n      Tests  248 passed (248)",
         {"passed": 248}),
        # The mixed line a mutation produces. This is the shape that parsed as nothing
        # and made the reverted-file counterfactual unrecordable.
        ("vitest red", "vitest",
         " Test Files  1 failed | 16 passed (17)\n"
         "      Tests  2 failed | 244 passed (246)",
         {"passed": 244, "not_passed": 2}),
        ("cargo", "cargo", "test result: ok. 22 passed; 0 failed; 0 ignored",
         {"passed": 22}),
        ("cargo two binaries", "cargo",
         "test result: ok. 17 passed; 0 failed\ntest result: ok. 5 passed; 0 failed",
         {"passed": 22}),
        ("no summary", "pytest", "collected 0 items\nno tests ran in 0.01s", None),
    ]
    for description, kind, output, expected in cases:
        got = parse_summary(kind, output)
        if got != expected:
            failures.append(f"{description}: parsed {got}, expected {expected}")

    # The refusal matters more than the parsing: a run that printed nothing usable must
    # not become a number, because a plausible number is exactly the defect this closes.
    if parse_summary("pytest", "") is not None:
        failures.append("an empty run produced a figure instead of None")

    # Provenance must be the line the figure came from, not the last line. Recording a
    # Node deprecation warning as the evidence for a vitest measurement proves nothing,
    # and that is what the first UI run wrote.
    noisy = ("(node:1) warning: something\n"
             " Test Files  19 passed (19)\n      Tests  248 passed (248)\n"
             "(Use `node --trace-warnings ...` to show where the warning was created)\n")
    recorded = summary_line("vitest", noisy)
    if "248 passed" not in recorded:
        failures.append(f"summary_line recorded {recorded!r} instead of the figure's line")

    # An end-to-end refusal, on a branch label that cannot exist. This exercises the real
    # code path (worktree creation fails) rather than a stub.
    ghost = measure_one(pathlib.Path("/nonexistent-clone"), "no-such-branch", "engine",
                        timeout=5)
    if "figures" in ghost or "error" not in ghost:
        failures.append(f"a failed run recorded figures: {ghost}")

    # The key migration, pinned by the defect that produced it: the manifest key gained a
    # clone prefix mid-run and nothing re-keyed the rows already on disk, so a superseded
    # `main|engine` (1074, measured at c39c79f) sat beside `laya-inspect|main|engine`
    # (1134, at e87abe4) and BOTH answered for "the base tree's count". The checker that
    # compares PR bodies against measurements was satisfied by a number describing a commit
    # two revisions old.
    legacy = {"entries": {
        "main|engine": {"clone": "laya-inspect", "branch": "main", "suite": "engine",
                        "sha": "c39c79f6aaa", "measured_at": "2026-09-25T05:00:00",
                        "figures": {"passed": 1074}},
        "laya-inspect|main|engine": {"clone": "laya-inspect", "branch": "main",
                                     "suite": "engine", "sha": "e87abe4ccc",
                                     "measured_at": "2026-09-25T08:00:00",
                                     "figures": {"passed": 1134}},
    }}
    # Through `load_manifest`, NOT by calling the migration directly: a mutant that replaced
    # the call site with `pass` passed the whole self-test when this only exercised the
    # function. Same gap as the binary-file loop in `audit_prepared_work`, and the same fix.
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as _tmp:
        on_disk = pathlib.Path(_tmp) / "counts.json"
        on_disk.write_text(json.dumps(legacy), encoding="utf-8")
        loaded = load_manifest(on_disk)
    keys = set(loaded["entries"])
    legacy = loaded
    if "main|engine" in keys:
        failures.append("a legacy key survived the migration")
    if not any(k.endswith("@c39c79f6") for k in keys):
        failures.append(f"the older commit's measurement was dropped ({sorted(keys)})")
    if legacy["entries"].get("laya-inspect|main|engine", {}).get("figures", {}).get("passed") != 1134:
        failures.append("the current measurement was overwritten by the older one")
    # A legacy row with nothing to re-key it by must stay visible rather than vanish.
    orphan = {"entries": {"branch|engine": {"branch": "b", "suite": "engine",
                                            "figures": {"passed": 1}}}}
    migrate_legacy_keys(orphan, pathlib.Path("/tmp/self-test-counts.json"))
    if "branch|engine" not in orphan["entries"]:
        failures.append("an un-keyable legacy row was silently deleted")

    failures += self_test_measurement()

    print("self-test:", "FAILED" if failures else "passed")
    for failure in failures:
        print(f"  FAILED: {failure}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work-dir", type=pathlib.Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--suite", choices=sorted(SUITES), default="engine")
    parser.add_argument("--only", action="append", default=[],
                        help="restrict to a branch (repeatable)")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--variant-label", default=None,
                        help="label a counterfactual measurement (e.g. 'two new tests "
                             "removed'); stored separately from the branch's own figure")
    parser.add_argument("--pre-suite", default=None,
                        help="shell command run in the worktree before the suite, for "
                             "the counterfactual a body asserts")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    _SCRATCH_HOME.mkdir(parents=True, exist_ok=True)
    try:
        _SCRATCH_HOME.chmod(0o700)
    except OSError:
        pass

    rows = plan_rows(args.work_dir)
    if not rows:
        print("error: could not read the submission plan", file=sys.stderr)
        return 2
    if args.only:
        rows = [r for r in rows if r[0] in set(args.only)]
    if not rows:
        print(f"error: --only matched no branch ({', '.join(args.only)})", file=sys.stderr)
        return 2

    manifest = load_manifest(args.manifest)
    print(f"measuring the {args.suite} suite on {len(rows)} tree(s); "
          f"manifest {args.manifest}")

    bad = 0
    for index, (branch, clone_name) in enumerate(rows, 1):
        clone = args.work_dir / clone_name
        if not (clone / ".git").exists():
            print(f"[{index}/{len(rows)}] {branch}: FAIL — {clone} is not a clone")
            bad += 1
            continue
        print(f"[{index}/{len(rows)}] {branch} …", flush=True)
        record = measure_one(clone, branch, args.suite, timeout=args.timeout,
                             variant=args.variant_label, pre_suite=args.pre_suite)
        store(manifest, record)
        if "figures" in record:
            mark = "green" if record.get("green") else "NOT GREEN"
            print(f"      {record['figures']} ({mark}) — {record['summary']}")
        else:
            print(f"      no figure recorded: {record.get('error')}")
            bad += 1
        # Written after every branch, so an interrupted run keeps what it earned.
        manifest["generated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        args.manifest.write_text(json.dumps(manifest, indent=1, sort_keys=True),
                                 encoding="utf-8")

    measured = sum(1 for e in manifest["entries"].values() if "figures" in e)
    print(f"\nmanifest: {measured} measurement(s) in {args.manifest}"
          + (f"; {bad} tree(s) produced no figure" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
