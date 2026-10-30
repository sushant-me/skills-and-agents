#!/usr/bin/env python3
"""Prove the whole prepared set works TOGETHER, in one command.

WHY THIS EXISTS. A clean text merge says nothing about the combination, so the set is checked
by merging every branch into one scratch tree and running the suites there. That was done by
hand four times (rounds 43, 44, 45 and 48) and it is slow enough to skip, fiddly enough to get
wrong, and it temporarily moves branches around in the user's clones — which is exactly the kind
of procedure that should be a tool with a `finally` block rather than a habit.

WHAT IT DOES, per clone that owns prepared branches:

  1. refuses to start on a dirty tree — uncommitted work is never at risk from this;
  2. creates a scratch branch off `main` and merges each prepared branch in plan order;
  3. fetches and merges the cross-clone branch (into `FETCH_HEAD`, so no permanent ref is left);
  4. runs that clone's checks on the combined tree;
  5. ALWAYS restores: the original branch is checked out again and the scratch branch deleted,
     on success, on failure, and on interrupt.

SAFETY. It never pushes, never opens a pull request, never touches a non-scratch branch, and
refuses to run against a dirty tree. `--plan` prints what it would do and exits.

    python3 compose_prepared_branches.py            # compose, test, restore
    python3 compose_prepared_branches.py --plan     # show the merge plan only
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import json
import pathlib
import re
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path.home() / "Work"
# The composed figures as measured, for the audit to check the index against.
DEFAULT_RECORD = WORK / "composed-counts.json"

# The engine suite reaches two pieces of the developer's real state on an unpatched
# checkout: it rewrites ~/.laya/settings.json, and — because the OS keychain is not under
# HOME — its teardown calls delete_mcp_token(), which removes the real MCP bearer token.
# Measured: 34 passing tests, token gone. So a scratch HOME *and* an in-memory keyring
# backend are set for every pytest run, whether or not the isolation branch is in the
# composition: that branch is the fix, this is the guard. HOME alone was here first and
# is not sufficient — redirecting it does nothing to a per-user keychain daemon. The
# backend is importable through PYTHONPATH because the child interpreter has to find it.
# The scratch HOME is uid-suffixed so two users on one machine do not share test state.
_SCRATCH_HOME = (f"/tmp/laya-verify-home-{os.getuid()}"
                 if hasattr(os, "getuid") else "/tmp/laya-verify-home")
_PYTHONPATH = [str(HERE)]
if os.environ.get("PYTHONPATH"):
    _PYTHONPATH.append(os.environ["PYTHONPATH"])
OS_ENV = {
    "HOME": _SCRATCH_HOME,
    "USERPROFILE": _SCRATCH_HOME,
    "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
    "PYTHON_KEYRING_BACKEND": "memkeyring.InMemoryKeyring",
}
CHECKS: dict[str, tuple[tuple[str, list[str], str], ...]] = {
    "laya-inspect": (
        ("engine suite", ["ENGINE_PY", "-m", "pytest", "-q"], "engine"),
        ("rust shell", ["cargo", "test", "--lib"], "ui/src-tauri"),
        ("ui unit tests", ["npm", "test"], "ui"),
        ("ui typecheck", ["npm", "run", "check"], "ui"),
        ("n8n entity check", ["node", "n8n/tests/github-ingestion-entity.mjs"], "."),
    ),
    "laya-chat": (
        ("engine suite", ["ENGINE_PY", "-m", "pytest", "-q"], "engine"),
        ("ui unit tests", ["npm", "test"], "ui"),
        ("ui typecheck", ["npm", "run", "check"], "ui"),
    ),
}


def plan() -> list[tuple[str, str]]:
    """(clone, branch) pairs, in the order the submit tool would ship them."""
    spec = importlib.util.spec_from_file_location("spw", HERE / "submit_prepared_work.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [(clone, branch) for branch, clone, _, _ in module.PLAN]


def git(clone: pathlib.Path, *args: str, check: bool = True) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True)
    output = (proc.stdout + proc.stderr).strip()
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {output}")
    return proc.returncode, output


def run_check(clone: pathlib.Path, label: str, argv: list[str], cwd: str,
              timeout: int = 1800) -> tuple[str, str, str]:
    where = clone / cwd if cwd != "." else clone
    # Resolved against the CLONE, not the check's cwd: `where` is already `<clone>/engine`, so
    # joining the interpreter path onto it produced `<clone>/engine/engine/.venv/...`.
    argv = [str(clone / "engine/.venv/bin/python") if a == "ENGINE_PY" else a for a in argv]
    # The scratch HOME is for pytest alone. Applying it to every check broke `cargo`, which
    # resolves its toolchains through `$HOME/.rustup` — rustup reported "run 'rustup default
    # stable'" and the composed run read as a Rust failure that did not exist.
    uses_engine_python = any(a.endswith("engine/.venv/bin/python") for a in argv)
    env = {**os.environ, **OS_ENV} if uses_engine_python else dict(os.environ)
    started = time.time()
    try:
        proc = subprocess.run(argv, cwd=str(where), capture_output=True, text=True,
                              timeout=timeout, env=env)
        code = proc.returncode
        output = (proc.stdout + proc.stderr).strip().splitlines()
    except subprocess.TimeoutExpired:
        code, output = 124, [f"timed out after {timeout}s"]
    except (OSError, subprocess.SubprocessError) as exc:
        code, output = 125, [str(exc)]
    named = [l.strip() for l in output if l.strip().startswith("FAILED")]
    if code and named:
        detail = "; ".join(named[:3])
    else:
        # Prefer a summary line: `npm test` ends with a node warning, so "the last line" is
        # not the result anyone wants to read.
        # A RESULT line, in preference order — "Tests 267 passed (267)", "test result: ok.
        # 22 passed", "svelte-check found 0 errors". Falling back to any line containing
        # "warning" was the first attempt and it reported npm's node warning as the outcome.
        import re as _re
        result = [l.strip() for l in output
                  if _re.search(r"\d+ passed|test result:|svelte-check found|all checks passed", l)]
        detail = (result[-1] if result else
                  next((l.strip() for l in reversed(output) if l.strip()), ""))
    return ("PASS" if code == 0 else "FAIL", detail[:130], f"{time.time() - started:.1f}s")


def compose(clone_dir: pathlib.Path, branches: list[str], cross: list[tuple[pathlib.Path, str]],
            plan_only: bool) -> tuple[bool, list[str], dict]:
    """Merge everything into a scratch branch in `clone_dir`.

    Returns (ok, lines, record). The record is the structured version of what the lines
    say — each check's status, detail and wall time, plus the combined diffstat — because
    until round 66 the composed figures (**1211 passed**, **49 files +5432 / −189**) existed
    only as prose in PREPARED-WORK-INDEX.md and nowhere a machine could read them. A number
    that lives only in a sentence drifts silently the moment a branch moves.
    """
    lines: list[str] = []
    record: dict = {"clone": clone_dir.name, "branches": list(branches), "checks": []}
    code, dirty = git(clone_dir, "status", "--porcelain")
    if dirty:
        return False, [f"{clone_dir.name}: REFUSING — working tree is dirty "
                       f"({len(dirty.splitlines())} file(s)); nothing was changed"], record
    _, original = git(clone_dir, "branch", "--show-current")
    scratch = f"verify/composed-{time.strftime('%Y%m%dT%H%M%S')}"
    _, base = git(clone_dir, "rev-parse", "--short", "main")
    lines.append(f"{clone_dir.name}: scratch {scratch} off main ({base}); "
                 f"original branch {original!r} will be restored")
    if plan_only:
        for branch in branches:
            lines.append(f"    would merge {branch}")
        for source, branch in cross:
            lines.append(f"    would fetch+merge {branch} from {source.name}")
        record["plan_only"] = True
        return True, lines, record

    git(clone_dir, "checkout", "-q", "-b", scratch, "main")
    try:
        for branch in branches:
            try:
                git(clone_dir, "merge", "--no-edit", "-q", branch)
                lines.append(f"    merged {branch}")
            except RuntimeError as exc:
                git(clone_dir, "merge", "--abort", check=False)
                record["conflict"] = f"merging {branch}: {exc}"
                return False, lines + [f"    CONFLICT merging {branch}: {exc}"], record
        for source, branch in cross:
            # FETCH_HEAD rather than a named ref: the other clone's branch is not mirrored
            # into this one, so nothing permanent is left behind.
            try:
                subprocess.run(["git", "-C", str(clone_dir), "fetch", "-q", str(source), branch],
                               capture_output=True, text=True, check=True)
                git(clone_dir, "merge", "--no-edit", "-q", "FETCH_HEAD")
                lines.append(f"    merged {branch} (from {source.name})")
            except (RuntimeError, subprocess.CalledProcessError) as exc:
                git(clone_dir, "merge", "--abort", check=False)
                record["conflict"] = f"merging {branch} from {source.name}: {exc}"
                return (False, lines
                        + [f"    CONFLICT merging {branch} from {source.name}: {exc}"], record)

        _, stat = git(clone_dir, "diff", "--stat", f"main...HEAD")
        summary = stat.splitlines()[-1].strip() if stat else "no changes"
        lines.append(f"    combined: {summary}")
        record["combined"] = summary
        _, head = git(clone_dir, "rev-parse", "--short", "HEAD")
        record["composed_sha"] = head
        ok = True
        for label, argv, cwd in CHECKS.get(clone_dir.name, ()):
            status, detail, wall = run_check(clone_dir, label, argv, cwd)
            lines.append(f"    {status:<4} {label:<18} {wall:>7}  {detail}")
            record["checks"].append({"label": label, "status": status, "detail": detail,
                                     "wall": wall})
            ok = ok and status == "PASS"
        return ok, lines, record
    finally:
        # Restore unconditionally: success, failure, and Ctrl-C all come through here.
        git(clone_dir, "checkout", "-q", original or "main", check=False)
        git(clone_dir, "branch", "-D", scratch, check=False)
        _, after = git(clone_dir, "branch", "--show-current")
        _, state = git(clone_dir, "status", "--porcelain")
        lines.append(f"    restored to {after!r}; tree "
                     f"{'clean' if not state else 'DIRTY — investigate'}")


def self_test() -> int:
    """Prove the composed verdict can be RED — this tool's green is the headline evidence.

    It had no self-test at all until round 65, which is the worst version of the gap the
    mutation sweep exists for: the tool that merges twelve branches and runs their suites
    was the one artifact whose "COMPOSED SET IS GREEN" nothing could falsify. Every case
    below is built on a throwaway repository, so nothing here touches the real clones.
    """
    import contextlib
    import io
    import tempfile

    # `plan` is patched below, so it needs the same declaration; without it the save
    # `saved_plan = plan` reads a local that the lambda assignment made unbound.
    global WORK, CHECKS, plan
    print("self-test: the composed verdict can be red, and restores what it touched")
    failures = 0

    def make_repo(base: pathlib.Path, name: str) -> pathlib.Path:
        repo = base / name
        repo.mkdir()
        def g(*args: str) -> None:
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e",
                            "-c", "user.name=t", *args], capture_output=True)
        g("init", "-q", "-b", "main")
        (repo / "f.txt").write_text("one\ntwo\nthree\n")
        g("add", "-A"); g("commit", "-q", "-m", "base")
        return repo

    def branch(repo: pathlib.Path, name: str, text: str) -> None:
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", name, "main"],
                       capture_output=True)
        (repo / "f.txt").write_text(text)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e", "-c", "user.name=t",
                        "commit", "-qam", name], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"],
                       capture_output=True)

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        repo = make_repo(base, "tempclone")

        # 1. A dirty tree is refused before anything moves.
        (repo / "f.txt").write_text("dirty\n")
        ok, lines, _rec = compose(repo, ["main"], [], plan_only=False)
        if ok or not any("REFUSING" in ln for ln in lines):
            print(f"  FAILED: a dirty tree was not refused ({ok}, {lines})")
            failures += 1
        else:
            print("  ok: a dirty working tree is refused and nothing is changed")
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "f.txt"],
                       capture_output=True)

        # 2. Two branches that conflict: the verdict must be red, and the tree restored.
        branch(repo, "topic-a", "one\nAAA\nthree\n")
        branch(repo, "topic-b", "one\nBBB\nthree\n")
        ok, lines, _rec = compose(repo, ["topic-a", "topic-b"], [], plan_only=False)
        if ok or not any("CONFLICT" in ln for ln in lines):
            print(f"  FAILED: a conflicting merge did not turn the verdict red ({ok})")
            failures += 1
        else:
            print("  ok: a conflicting merge reports CONFLICT and returns not-ok")
        current = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"],
                                 capture_output=True, text=True).stdout.strip()
        scratch = subprocess.run(["git", "-C", str(repo), "branch", "--list",
                                  "verify/composed-*"], capture_output=True,
                                 text=True).stdout.strip()
        if current != "main" or scratch:
            print(f"  FAILED: not restored (on {current!r}, scratch {scratch!r})")
            failures += 1
        else:
            print("  ok: the clone is back on its branch with no scratch branch left")

        # 3. A clean merge whose SUITE fails must also be red. The check is injected for
        #    this clone's name, which is how a real failure reaches the verdict.
        saved_checks = dict(CHECKS)
        CHECKS["tempclone"] = (("synthetic suite",
                                [sys.executable, "-c",
                                 "import sys; print('1 failed, 3 passed'); sys.exit(1)"],
                                "."),)
        try:
            ok, lines, rec = compose(repo, ["topic-a"], [], plan_only=False)
            if ok or not any("FAIL" in ln for ln in lines):
                print(f"  FAILED: a failing suite did not turn the verdict red ({ok})")
                failures += 1
            elif not rec.get("checks") or rec["checks"][0]["status"] != "FAIL":
                # The record is what the audit checks the index's composed figures
                # against, so it has to carry the figure, not just the line.
                print(f"  FAILED: the record does not carry the check result ({rec})")
                failures += 1
            elif not re.search(r"\d+ files? changed", rec.get("combined", "")):
                print(f"  FAILED: the record has no combined diffstat ({rec.get('combined')})")
                failures += 1
            else:
                print("  ok: a failing suite in the composed tree returns not-ok, and the "
                      "record carries the figure")
        finally:
            CHECKS.clear(); CHECKS.update(saved_checks)

        # 4. --plan must create nothing at all.
        before = subprocess.run(["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
                                capture_output=True, text=True).stdout.split()
        ok, lines, _rec = compose(repo, ["topic-a"], [], plan_only=True)
        after = subprocess.run(["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
                               capture_output=True, text=True).stdout.split()
        if not ok or before != after:
            print(f"  FAILED: --plan changed the repository ({before} -> {after})")
            failures += 1
        else:
            print("  ok: --plan reports the merge plan and creates nothing")

        # 4b. run_check must report the RESULT line, not whatever printed last. npm ends
        #     with a node warning, and "the last line" reported that as the outcome.
        noisy = [sys.executable, "-c",
                 "print('Tests  22 passed (22)');"
                 "print('(node:1) DeprecationWarning: something')"]
        status, detail, _wall = run_check(repo, "synthetic noisy", noisy, ".")
        if status != "PASS" or "22 passed" not in detail or "DeprecationWarning" in detail:
            print(f"  FAILED: run_check reported {status} {detail!r} for a noisy pass")
            failures += 1
        else:
            print("  ok: run_check reports the result line, not the trailing warning")
        status, detail, _wall = run_check(
            repo, "synthetic nodeid",
            [sys.executable, "-c",
             "import sys; print('FAILED tests/test_a.py::test_b - boom');"
             "print('1 failed in 0.01s'); sys.exit(1)"], ".")
        if status != "FAIL" or "test_a.py::test_b" not in detail:
            print(f"  FAILED: a failing check lost its nodeid ({status} {detail!r})")
            failures += 1
        else:
            print("  ok: a failing check carries the failing nodeid")

        # 5. END TO END through main(): the headline line must be able to say FAILURES.
        #    `plan()` and `WORK` are the only two things main() reads from the world.
        saved_plan, saved_work = plan, WORK
        plan = lambda: [("tempclone", "topic-a"), ("tempclone", "topic-b")]  # noqa: E731
        WORK = base
        try:
            buffer = io.StringIO()
            scratch_record = base / "self-test-counts.json"
            # `--record` is passed explicitly because `main` writes the composed figures to
            # the PRODUCTION path by default, and the first version of this test called
            # `main([])`: the self-test's throwaway composition overwrote the real
            # composed-counts.json, so the audit then checked the index against "tempclone".
            # A self-test must not write where the real tool reads.
            with contextlib.redirect_stdout(buffer):
                code = main(["--record", str(scratch_record)])
        finally:
            plan, WORK = saved_plan, saved_work
        out = buffer.getvalue()
        if code != 1 or "COMPOSED SET HAS FAILURES" not in out:
            print(f"  FAILED: main() reported code {code} and did not print FAILURES")
            failures += 1
        elif "COMPOSED SET IS GREEN" in out:
            print("  FAILED: main() printed GREEN and FAILURES for the same run")
            failures += 1
        elif not scratch_record.is_file():
            print("  FAILED: main() did not write the record it was told to write")
            failures += 1
        else:
            print("  ok: main() exits 1 and prints COMPOSED SET HAS FAILURES when a merge "
                  "conflicts")

    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true", help="print the merge plan and exit")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the verdict can be red, on a throwaway repository")
    parser.add_argument("--record", type=pathlib.Path, default=DEFAULT_RECORD,
                        help="where to write the measured composed figures")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()

    pairs = plan()
    if not pairs:
        print("no prepared branches in the plan")
        return 1

    by_clone: dict[str, list[str]] = {}
    for clone, branch in pairs:
        by_clone.setdefault(clone, []).append(branch)

    # The cross-clone merges: a branch that lives in one clone and belongs in another's
    # composition, because that is where the combined behaviour matters. Built from the
    # declared pairs directly — the first version searched for them inside a triple loop and
    # listed the same pair nine times, which `--plan` is what caught.
    cross: dict[str, list[tuple[pathlib.Path, str]]] = {}
    for landing, branch in sorted(CROSS_CLONE_PAIRS):
        source = next((c for c, bs in by_clone.items() if branch in bs and c != landing), None)
        if source:
            cross.setdefault(landing, []).append((WORK / source, branch))

    print(f"composing {len(pairs)} prepared branches across {len(by_clone)} clone(s)\n")
    all_ok = True
    records: list[dict] = []
    for clone_name, branches in by_clone.items():
        # The chat branch is composed into laya-inspect for the combined check, so
        # laya-chat composes only its own.
        ok, lines, record = compose(WORK / clone_name, branches,
                                    cross.get(clone_name, []), args.plan)
        for line in lines:
            print(line)
        print()
        records.append(record)
        all_ok = all_ok and ok

    if args.plan:
        print("plan only — nothing was created, merged or changed")
        return 0

    # Written whether or not the set is green: a red composition's figures are exactly the
    # ones a reader needs, and the index claims green ones.
    try:
        args.record.write_text(json.dumps({
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "ok": all_ok,
            "records": records,
        }, indent=1, sort_keys=True), encoding="utf-8")
        print(f"recorded: {args.record}")
    except OSError as exc:
        print(f"could not write {args.record}: {exc}")

    print("COMPOSED SET IS GREEN" if all_ok else "COMPOSED SET HAS FAILURES")
    return 0 if all_ok else 1


# (clone the branch lands in, branch) — pairs that must be checked together even though they
# live in different clones. Mirrors the declarations in audit_prepared_work.py.
CROSS_CLONE_PAIRS = {
    ("laya-inspect", "feat/full-page-coding-chat"),
}


if __name__ == "__main__":
    raise SystemExit(main())
