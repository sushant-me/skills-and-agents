#!/usr/bin/env python3
"""One command that runs every check this work has, so a round cannot silently skip one.

WHY THIS EXISTS. The checks accumulated across three rounds and nothing ran all of them. Each
round ran a different subset — surface rules here, claim verification there, the suites when a
count was in question — so "everything is green" meant "everything I happened to run is
green". That is the same failure shape as the figures this work keeps finding: a claim that is
true of the sample and unchecked outside it. This is the entry point that makes the sample the
whole set.

It also makes skipping visible. An online check that is not run prints SKIP with the reason,
so a green table that omitted the most important check — the one that compares every claim to
the source it names — cannot be mistaken for a green run.

    python3 tools/verify_everything.py              # every offline check
    python3 tools/verify_everything.py --online     # plus the ones that read the network
    python3 tools/verify_everything.py --self-test  # prove this runner can report a failure
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_WORK_DIR = pathlib.Path.home() / "Work"
# Listed rather than globbed: `bughunter` sits in the same directory with its own suite and is
# not this work's to keep green. Anything with a suite that is NOT listed is printed as
# unwatched rather than quietly excluded.
SUITE_REPOS = (
    "agentbound", "agent-review-sample", "beyond-attention", "mcpaudit",
    "mcp-nameguard", "policygate", "tool-boundary-corpus", "trajectorycheck",
)
PRESET_TOOLS = (
    "check_laya_home", "verify_claims", "audit_prepared_work",
    "submit_prepared_work", "handoff_status", "check_pr_bodies",
    "measure_prepared_counts",
    # The mutation claims the PR bodies make ("disable this guard and exactly these tests
    # fail") are the strongest thing any of them says, and nothing checked them until
    # round 68 — where two turned out to be wrong by one and by three.
    "verify_mutations",
    # The composed run is this workspace's headline evidence, and until round 65 the tool
    # that produces it had no self-test at all — nothing could falsify "COMPOSED SET IS
    # GREEN". Its self-test builds a throwaway clone and drives main() to FAILURES.
    "compose_prepared_branches",
)
OFFLINE_CHECKS = (
    ("reputation: surface rules",
     ["reputation/check_surfaces.py", "--min-surfaces", "22"]),
    ("reputation: writeups index", ["reputation/check_writeups_index.py"]),
    ("reputation: the writeups guard can fire",
     ["reputation/check_writeups_index.py", "--self-test"]),
    ("reputation: secret scan does not flag itself",
     ["reputation/check_secrets.py", "--self-test"]),
    # The Laya work was outside this battery altogether, which made "all checks passed" a
    # statement about the side projects. The audit is offline and cheap; the composed run is
    # opt-in because it merges ten branches and runs two engine suites.
    ("laya: prepared work audit",
     [str(HERE / "audit_prepared_work.py"), "--offline"]),
    # The PR bodies are the one artefact nothing else verifies, and two of them were
    # found asserting things the code did not do. ~40 s to check all twelve.
    # `--require-counts` makes a missing measurement manifest a FAILURE rather than a
    # note: the quoted "N passed" figures are the numbers a maintainer weighs, and a
    # check that silently turns itself off when its input is absent is the exact shape
    # this workspace keeps publishing about. The manifest is produced by
    # measure_prepared_counts.py, which runs the suites; it is minutes, so it is a
    # deliberate act rather than part of this battery.
    ("laya: PR bodies match their branches",
     [str(HERE / "check_pr_bodies.py"), "--require-counts"]),
    # Disable one guard at a time in the preset tools and require each tool's own
    # self-test to notice. It exists because round 63 found a mutant that emptied a
    # check's call site and passed the whole self-test, and the first sweep found ten
    # more — five of them the `raise Stop` guards inside submit_prepared_work's
    # preflight, i.e. the refusals that keep a bad PR off the fork. ~11 s.
    ("preset tools: the self-tests actually guard",
     [str(HERE / "mutation_sweep.py")]),
)
ONLINE_CHECKS = (
    ("reputation: every claim vs its source", ["reputation/verify_evidence.py"]),
    ("reputation: no dead links", ["reputation/check_links.py"]),
    ("reputation: HackingHub figure matches the board",
     ["reputation/sync_hackinghub.py"]),
)


class Check:
    def __init__(self, label, argv, cwd=None, timeout=900, online=False, retry=False,
                 env=None):
        self.label, self.argv, self.cwd = label, argv, cwd
        self.timeout, self.online, self.retry = timeout, online, retry
        self.env = env


def _laya_suite_env(directory: pathlib.Path) -> dict | None:
    """Scratch HOME + in-memory keychain for the Laya engine suite, or None elsewhere.

    A plain ``pytest`` on this repo reaches two pieces of the developer's real state:
    it rewrites ``~/.laya/settings.json``, and — because the OS keychain is not under
    ``HOME`` — the teardown in ``tests/test_mcp_http.py`` deletes the real MCP bearer
    token from it. Measured: 34 passing tests, token gone. Both need defending here
    rather than assumed away, because the branch that fixes them inside the repo is
    not merged and this battery runs against every branch.

    The HOME is stable across runs on purpose: redirecting it also relocates
    ChromaDB's model cache, and a fresh directory per run made the suite take 241s
    instead of 43s.
    """
    if not (directory / "engine" / "laya" / "security" / "keychain.py").is_file():
        return None
    home = RUN_LOG.parent / "suite-home"
    home.mkdir(parents=True, exist_ok=True)
    try:
        home.chmod(0o700)
    except OSError:
        pass
    pythonpath = [str(HERE)]
    if os.environ.get("PYTHONPATH"):
        pythonpath.append(os.environ["PYTHONPATH"])
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": os.pathsep.join(pythonpath),
        "PYTHON_KEYRING_BACKEND": "memkeyring.InMemoryKeyring",
    }


def build_checks(work: pathlib.Path, online: bool,
                 compose: bool = False) -> tuple[list[Check], list[str]]:
    checks: list[Check] = []
    for label, argv in OFFLINE_CHECKS:
        checks.append(Check(label, argv, cwd=work))
    for name in PRESET_TOOLS:
        checks.append(Check(f"preset tool: {name}",
                            [str(HERE / f"{name}.py"), "--self-test"], cwd=work))
    for repo in SUITE_REPOS:
        directory = work / repo
        if not (directory / "tests").is_dir():
            continue
        # The repository's own environment when it has one, otherwise the interpreter running
        # this script: agent-review-sample's suite is stdlib-only and passes under a plain
        # pytest, and requiring a per-repo venv would have excluded it for no reason.
        interpreter = directory / ".venv" / "bin" / "python"
        exe = str(interpreter) if interpreter.exists() else sys.executable
        checks.append(Check(f"suite: {repo}", [exe, "-m", "pytest", "-q"],
                            cwd=directory, retry=True,
                            env=_laya_suite_env(directory)))
    if online:
        for label, argv in ONLINE_CHECKS:
            checks.append(Check(label, argv, cwd=work, online=True))
        checks.append(Check("laya: prepared branches vs upstream",
                            [str(HERE / "verify_claims.py")], cwd=work, online=True))
    if compose:
        # Minutes, and it runs the Laya engine suite eight times over. Gate it with the
        # other expensive path rather than slowing every casual run.
        checks.append(Check("laya: the bodies' mutation claims",
                            [str(HERE / "verify_mutations.py")], cwd=work, timeout=3600))
        # Merges every prepared branch into a scratch tree in each clone, runs the engine,
        # Rust and UI suites there, and restores the clones. Minutes, not seconds.
        checks.append(Check("laya: the whole set composed",
                            [str(HERE / "compose_prepared_branches.py")], cwd=work,
                            timeout=3600))

    # Anything else with a suite is reported, so the listed set cannot go quietly stale —
    # trajectorycheck and mcpaudit were each missing from the push report for a round.
    unwatched = []
    for directory in sorted(p for p in work.iterdir() if p.is_dir()):
        if directory.name in SUITE_REPOS or not (directory / "tests").is_dir():
            continue
        if (directory / ".git").is_dir():
            unwatched.append(directory.name)
    return checks, unwatched


def command_for(check: Check) -> list[str]:
    """The argv to execute. One place, because the retry path ran the script directly and
    got `PermissionError` on a .py file with no shebang — the first run worked and the retry
    did not, which is the kind of difference only a test of the retry finds."""
    if check.argv[0].endswith(".py"):
        return [sys.executable] + check.argv
    return check.argv


def run(checks: list[Check]) -> list[tuple[str, str, str]]:
    def invoke(check):
        env = {**os.environ, **check.env} if check.env else None
        return subprocess.run(command_for(check),
                              cwd=str(check.cwd) if check.cwd else None,
                              capture_output=True, text=True,
                              timeout=check.timeout, env=env)

    results = []
    for check in checks:
        try:
            # `cwd=str(check.cwd)` when it is None makes the literal directory "None", which
            # does not exist, so every check failed for the wrong reason and the detail line
            # was the FileNotFoundError rather than the check's own message. The self-test
            # reported both symptoms on its first run.
            proc = invoke(check)
            code = proc.returncode
            output = (proc.stdout + proc.stderr).strip().splitlines()
        except subprocess.TimeoutExpired:
            code, output = 124, [f"timed out after {check.timeout}s"]
        except (OSError, subprocess.SubprocessError) as exc:
            code, output = 125, [str(exc)]
        # A failing suite's summary line says "1 failed" and nothing else, which forces a
        # re-run to learn WHICH test — and a test that fails once in a while is exactly the
        # one worth naming. pytest prints `FAILED <nodeid>` for each.
        named = [l.strip() for l in output if l.strip().startswith("FAILED")]
        if code != 0 and named:
            detail = "; ".join(named[:3])
        else:
            detail = next((l.strip() for l in reversed(output) if l.strip()), "")

        # A suite that fails and then passes on the same code is flaky, and reporting it as a
        # failure sends someone to look for a defect in the product rather than in the test.
        # Reporting it as a pass hides it. `FLAKY` says which, and still counts against the
        # run: something in that suite depends on something it should not. This is not
        # hypothetical — mcp-nameguard failed once here with "1 failed, 81 passed" and has not
        # reproduced it in nine runs since, including a deliberately loaded one.
        status = "PASS" if code == 0 else "FAIL"
        if code != 0 and check.retry:
            retry = invoke(check)
            if retry.returncode == 0:
                status = "FLAKY"
                detail = "failed once then passed — " + detail
        results.append((check.label, status, detail[:140]))
    return results


RUN_LOG = pathlib.Path(os.environ.get("DSH_HOME", pathlib.Path.home() / ".dsh")) \
    / "verify-runs"
RUN_LOG_KEEP = 30


def record_run(results: list[tuple[str, str, str]], online: bool) -> pathlib.Path | None:
    """Persist this run's results, failures included.

    Twice now a suite failed inside a battery, was reported only as "1 of 20 failed", and the
    detail line — which names the failing test — was lost to a truncated terminal before anyone
    read it. The failure did not reproduce either time, so the evidence that would have
    identified it went with it. Writing every run to disk costs nothing and makes the next
    occurrence retrievable after the fact, whether or not anyone was watching.
    """
    try:
        RUN_LOG.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        path = RUN_LOG / f"{stamp}.json"
        path.write_text(json.dumps({
            "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "online": online,
            "load": machine_load(),
            "results": [{"check": c, "status": s_, "detail": d} for c, s_, d in results],
        }, indent=2), encoding="utf-8")
        old = sorted(RUN_LOG.glob("*.json"))[:-RUN_LOG_KEEP]
        for stale in old:
            stale.unlink()
        return path
    except OSError:
        return None


def machine_load() -> dict:
    """This machine's load and core count, recorded with every run.

    A run on 2026-09-25 reported `suite: beyond-attention PASS 351 passed in 713.97s`
    against a normal 17s, and a wall-clock figure 40x off reads as a defect in the
    suite. It was not: load average was 32.7 on 12 cores, because the user's own
    cipher-brute-force jobs (`glibcrand`, `lcg11`, `lcg18`) were saturating the box.
    Two consequences worth never re-deriving — timings from a loaded run are not
    comparable to any other run, and a *timing-dependent* test (the mcp-nameguard
    stderr race, measured at 0.5%-9.5% depending on load) flakes far more often here.
    Recording it means `--history` can say which runs were taken under load instead of
    a later round chasing a phantom flake.
    """
    try:
        one, five, fifteen = os.getloadavg()
    except (OSError, AttributeError):
        return {"cores": os.cpu_count()}
    cores = os.cpu_count() or 1
    return {"cores": cores, "load1": round(one, 2), "load5": round(five, 2),
            "load15": round(fifteen, 2), "saturated": one > cores}


def show_history(limit: int = 10) -> int:
    """Print the failing checks from recent runs, newest first."""
    runs = sorted(RUN_LOG.glob("*.json"))[-limit:] if RUN_LOG.is_dir() else []
    if not runs:
        print("no recorded runs yet")
        return 0
    shown = 0
    for path in reversed(runs):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        failed = [r for r in record["results"] if r["status"] != "PASS"]
        if not failed:
            continue
        shown += 1
        load = record.get("load") or {}
        under = ("  [taken under load: %.1f on %s cores]"
                 % (load["load1"], load["cores"])
                 if load.get("saturated") else "")
        print(f"{record['when']}  ({'online' if record['online'] else 'offline'}){under}")
        for r in failed:
            print(f"   {r['status']:<5} {r['check']}\n         {r['detail']}")
    if not shown:
        print(f"no failures in the last {len(runs)} recorded run(s)")
    return 0


def self_test() -> int:
    """Prove the runner reports a failure rather than only a success."""
    import tempfile
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        good = pathlib.Path(tmp) / "good.py"
        good.write_text("print('all good')\n")
        bad = pathlib.Path(tmp) / "bad.py"
        bad.write_text("import sys; print('one problem'); sys.exit(1)\n")
        flaky = pathlib.Path(tmp) / "flaky.py"
        marker = pathlib.Path(tmp) / "seen"
        flaky.write_text(
            "import pathlib, sys\n"
            f"m = pathlib.Path({str(marker)!r})\n"
            "if m.exists(): print('passed on retry'); sys.exit(0)\n"
            "m.write_text('x'); print('failed first'); sys.exit(1)\n")
        checks = [Check("synthetic pass", [str(good)]), Check("synthetic fail", [str(bad)]),
                  Check("synthetic flaky", [str(flaky)], retry=True)]
        results = run(checks)
        verdict = {label: status for label, status, _ in results}
        for label, expected in (("synthetic pass", "PASS"), ("synthetic fail", "FAIL"),
                                ("synthetic flaky", "FLAKY")):
            if verdict.get(label) != expected:
                print(f"  FAIL: {label} reported {verdict.get(label)}, expected {expected}")
                failures += 1
        detail = {label: text for label, _, text in results}
        if "one problem" not in detail.get("synthetic fail", ""):
            print("  FAIL: the failing check's own message was not carried into the report")
            failures += 1
    # The evidence path. Three separate mutations passed the self-test while disabling it:
    # the failing nodeid was no longer carried into the detail (round 48 exists precisely
    # because that name was lost twice), `record_run` wrote its JSON under a different
    # name, and `show_history` filtered every failure away. Each is checked here.
    with tempfile.TemporaryDirectory() as tmp:
        nodeid = pathlib.Path(tmp) / "nodeid.py"
        # The nodeid is deliberately NOT the last line: real pytest prints its
        # `=== short test summary info ===` block and then a `1 failed in 0.01s`
        # summary, so a detail built from the last line loses the test's name. With the
        # nodeid last, a mutation that dropped the FAILED-line extraction still passed.
        nodeid.write_text("import sys\n"
                          "print('FAILED tests/test_x.py::test_y - AssertionError: boom')\n"
                          "print('1 failed in 0.01s')\n"
                          "sys.exit(1)\n")
        one = run([Check("synthetic nodeid", [str(nodeid)])])
        if "tests/test_x.py::test_y" not in one[0][2]:
            print("  FAIL: the failing nodeid was not carried into the detail")
            failures += 1
        else:
            print("  ok: a failing pytest nodeid reaches the report, not just '1 failed'")

        # `record_run` and `show_history` read the module-level RUN_LOG at call time, so
        # redirecting it is enough — no need to write into the real history.
        global RUN_LOG
        saved_log = RUN_LOG
        try:
            RUN_LOG = pathlib.Path(tmp) / "verify-runs"
            written = record_run([("synthetic fail", "FAIL", "boom")], online=False)
            if not written or not written.is_file():
                print("  FAIL: a failing run was not written to disk")
                failures += 1
            elif RUN_LOG.glob("*.json") and not any(
                    "synthetic fail" in p_.read_text() for p_ in RUN_LOG.glob("*.json")):
                print("  FAIL: the recorded run does not contain its own failure")
                failures += 1
            else:
                print("  ok: a run is written to disk where --history can find it")
            import contextlib
            import io
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                show_history()
            if "synthetic fail" not in buffer.getvalue():
                # A failure nobody can read back is the round-48 defect: the run that broke
                # was recorded nowhere, and the nodeid went with it.
                print("  FAIL: --history did not surface a recorded failure")
                failures += 1
            else:
                print("  ok: --history surfaces a recorded failure")
        finally:
            RUN_LOG = saved_log

    if failures:
        print(f"self-test: {failures} check(s) failed")
        return 1
    print("self-test: a passing check reports PASS, a failing one reports FAIL with its own "
          "message, and one that fails then passes reports FLAKY — so a green table is not "
          "the only thing this can produce, and a flaky suite is not mistaken for a defect")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work-dir", type=pathlib.Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--online", action="store_true",
                        help="also run the checks that read the network")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--compose", action="store_true",
                        help="also merge every prepared branch and re-run the suites there")
    parser.add_argument("--history", action="store_true",
                        help="print the failing checks from recent runs and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.history:
        return show_history()

    work = args.work_dir.expanduser().resolve()
    checks, unwatched = build_checks(work, args.online, args.compose)
    results = run(checks)

    width = max(len(label) for label, _, _ in results) if results else 10
    print("=" * (width + 14))
    print(f"EVERY CHECK — {len(results)} run, work dir {work}")
    print("=" * (width + 14))
    for label, status, detail in results:
        print(f"  {label:<{width}}  {status}  {detail}")
    if not args.online:
        for label, _ in ONLINE_CHECKS:
            print(f"  {label:<{width}}  SKIP  needs --online")
    if unwatched:
        print(f"\n  with a suite but NOT in SUITE_REPOS (their green is not claimed here): "
              f"{', '.join(unwatched)}")

    load = machine_load()
    if load.get("saturated"):
        print(f"\n  ⚠ this machine is loaded ({load['load1']} on {load['cores']} cores): "
              f"the wall-clock figures above are not comparable to an idle run, and a "
              f"timing-dependent test will flake more often. Recorded with the run.")

    written = record_run(results, args.online)
    failed = [label for label, status, _ in results if status != "PASS"]
    flaky = [label for label, status, _ in results if status == "FLAKY"]
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} failed: {', '.join(failed)}")
        return 1
    if flaky:
        print(f"note: {len(flaky)} suite(s) failed once and passed on a retry — the suite is "
              f"flaky, which is a defect in the test: {', '.join(flaky)}")
    if written:
        print(f"recorded: {written}")
    print(f"all {len(results)} checks passed"
          + ("" if args.online else " (offline only — re-run with --online before shipping)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
