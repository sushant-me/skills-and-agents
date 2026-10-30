#!/usr/bin/env python3
"""One screen answering: what has been done, and what is still unshipped?

Why this exists
---------------
This work accumulated over many rounds, and almost none of it left the machine:
a handful of commits across several repositories, a set of prepared pull requests,
and a ledger of items blocked on the user's own credentials or decisions. All of
that lived in conversation scrollback. A reader returning after a long gap could
not tell what existed, what was verified, or what only they could do -- and the
one question worth asking ("what is waiting for me?") had no command.

Everything here is DERIVED, not remembered:

  * unpushed commits come from `git rev-list origin/<branch>..<branch>`, per
    repository, so a commit that is pushed simply stops appearing;
  * the prepared pull requests come from the submission plan in
    `submit_prepared_work.py`, so retiring a branch retires it here too;
  * the "needs you" list is read from the durable task ledger, not prose;
  * the verified state is the other tools' own `--self-test`, run live.

It touches nothing: every git call is read-only, and it never pushes, fetches to
a remote it writes to, or edits the ledger.

    python3 tools/handoff_status.py
    python3 tools/handoff_status.py --work-dir /path/to/work
    python3 tools/handoff_status.py --self-test
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_WORK_DIR = pathlib.Path.home() / "Work"
LEDGER = pathlib.Path(os.environ.get("DSH_HOME", pathlib.Path.home() / ".dsh")) \
    / "agent-tasks" / "tasks.json"
# The repositories this work touched. Listed rather than globbed so a clone that
# happens to sit in the work directory is not swept in — but a listed set is only
# as good as the round that last added to it: trajectorycheck was missing here, so
# the push it needed was invisible to this report until it was found by counting
# every sushant-me clone instead.
WATCHED = (
    "reputation", "profile-readme", "hire", "portfolio", "cv",
    "tool-boundary-corpus", "agentbound", "beyond-attention", "writeups",
    "trajectorycheck", "mcpaudit", "mcp-nameguard",
)


def run(args: list[str], cwd: pathlib.Path | None = None) -> str:
    try:
        out = subprocess.run(args, cwd=str(cwd) if cwd else None,
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def unwatched(work: pathlib.Path) -> list[tuple[str, int]]:
    """sushant-me clones with unpushed commits that WATCHED does not list.

    Twice a repository carrying work was missing from that list — trajectorycheck, then
    mcpaudit — so the push it needed was invisible in this report until something counted
    every clone by hand. Listing the set is fine; a listed set that nothing verifies is not,
    so the list is now checked against the thing it is a subset of.
    """
    found: list[tuple[str, int]] = []
    for repo in sorted(work.iterdir()):
        if repo.name in WATCHED or not (repo / ".git").is_dir():
            continue
        if "github.com/sushant-me/" not in run(["git", "-C", str(repo), "remote", "get-url", "origin"]):
            continue
        info = unpushed(repo)
        if info:
            found.append((repo.name, info[1]))
    return found


def unpushed(repo: pathlib.Path) -> tuple[str, int, list[str]] | None:
    """(branch, count, subjects) when the current branch is ahead of its upstream."""
    branch = run(["git", "-C", str(repo), "branch", "--show-current"])
    if not branch:
        return None
    upstream = f"origin/{branch}"
    if not run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", upstream]):
        return None
    count = run(["git", "-C", str(repo), "rev-list", "--count", f"{upstream}..{branch}"])
    if not count or count == "0":
        return None
    subjects = run(["git", "-C", str(repo), "log", "--oneline",
                    f"{upstream}..{branch}"]).splitlines()
    return branch, int(count), subjects


def submission_plan() -> tuple[list[tuple[str, str, str, str]], str | None]:
    """The prepared branches, imported from the submit tool so there is one list."""
    path = HERE / "submit_prepared_work.py"
    try:
        spec = importlib.util.spec_from_file_location("_submit_plan", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_submit_plan"] = module
        spec.loader.exec_module(module)
        return list(module.PLAN), None
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return [], f"could not read the submission plan from {path.name}: {exc}"


def other_unpushed_branches(work: pathlib.Path, prepared: set[str]) -> list[tuple[str, str, int]]:
    """(repo, branch, commits) for work committed to a branch that is not on the remote.

    The report above follows the CHECKED-OUT branch, which silently misses work parked
    elsewhere: a fix committed to `fix/stdio-stderr-tail-race` while the clone sat on `main`
    appeared in no list at all, and it is exactly the work that needs pushing. Branches already
    listed as prepared pull requests are excluded, since those are reported above.
    """
    found: list[tuple[str, str, int]] = []
    for name in WATCHED:
        repo = work / name
        if not (repo / ".git").is_dir():
            continue
        # run() returns a string here (the submit tool's two-tuple runner is a different
        # helper); unpacking it as a pair raised inside main and the section never printed.
        branches = run(["git", "-C", str(repo), "for-each-ref",
                        "--format=%(refname:short)", "refs/heads"])
        if not branches:
            continue
        for branch in branches.splitlines():
            branch = branch.strip()
            if not branch or branch in ("main", "master") or branch in prepared:
                continue
            count = run(["git", "-C", str(repo), "rev-list", "--count",
                         f"origin/main..{branch}"])
            try:
                ahead = int(count.strip() or "0")
            except ValueError:
                continue
            if ahead > 0:
                found.append((name, branch, ahead))
    return found


def ledger_items(statuses: tuple[str, ...] = ("blocked",),
                 priorities: tuple[str, ...] = ()) -> list[dict]:
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("tasks", data) if isinstance(data, dict) else data
    out = []
    for item in items:
        if item.get("status") not in statuses:
            continue
        if priorities and item.get("priority") not in priorities:
            continue
        out.append(item)
    return out


def waiting_on_you() -> list[dict]:
    """Blocked items, plus OPEN HIGH ones -- the second half is not optional.

    The first version listed only `blocked`, and the most urgent item in the entire
    ledger (a live credential exposure) is filed as `open` + `high`, so the report
    omitted exactly the thing it existed to surface. `blocked` means "cannot
    proceed"; `open`+`high` means "this is yours and it matters". Both belong here,
    actionable first.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for group in (ledger_items(statuses=("open",), priorities=("high",)),
                  ledger_items(statuses=("blocked",))):
        for item in group:
            key = item.get("id") or item.get("title", "")
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def self_test() -> int:
    """Prove the unpushed detector fires on a commit, and not on a pushed one."""
    import tempfile

    print("self-test: unpushed detection")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp) / "clone"
        repo.mkdir()

        def g(*args: str) -> str:
            return run(["git", "-C", str(repo), "-c", "user.email=t@example.com",
                        "-c", "user.name=t", *args])

        g("init", "-q", "-b", "main")
        (repo / "f.txt").write_text("x\n")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        g("update-ref", "refs/remotes/origin/main", "main")

        if unpushed(repo) is None:
            print("  ok: a branch level with its upstream reports nothing")
        else:
            print("  FAILED: a level branch was reported as unpushed")
            failures += 1

        (repo / "f.txt").write_text("y\n")
        g("add", "-A")
        g("commit", "-q", "-m", "one more")
        found = unpushed(repo)
        if found and found[1] == 1 and "one more" in " ".join(found[2]):
            print("  ok: one unpushed commit is detected, with its subject")
        else:
            print(f"  FAILED: expected one unpushed commit, got {found}")
            failures += 1

        # A branch whose upstream ref does not exist must report NOTHING. Disabling that
        # guard passed the whole self-test, which meant a repository with no upstream
        # fetched could be counted and reported as carrying unpushed work — a false item
        # on the very list this tool exists to keep honest.
        g("update-ref", "-d", "refs/remotes/origin/main")
        if unpushed(repo) is None:
            print("  ok: an absent upstream ref reports nothing, not a bogus count")
        else:
            print(f"  FAILED: a missing upstream produced {unpushed(repo)}")
            failures += 1
        # `main` itself, so the branch is level with its upstream and reports nothing.
        # Pointing it at `main~1` first was wrong: that makes the branch one commit ahead,
        # which the tool correctly reports — the bad expectation was mine, not the code's.
        g("update-ref", "refs/remotes/origin/main", "main")
        if unpushed(repo) is None:
            print("  ok: a branch level with an existing upstream reports nothing")
        else:
            print(f"  FAILED: a level branch produced {unpushed(repo)}")
            failures += 1

    # A missing ledger must read as "none", never as a crash.
    saved = globals()["LEDGER"]
    try:
        globals()["LEDGER"] = pathlib.Path("/nonexistent/tasks.json")
        if ledger_items() == []:
            print("  ok: an unreadable ledger reports no items rather than failing")
        else:
            print("  FAILED: an unreadable ledger produced items")
            failures += 1
    finally:
        globals()["LEDGER"] = saved

    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work-dir", type=pathlib.Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    work = args.work_dir.expanduser().resolve()

    # ── 1. unpushed commits ────────────────────────────────────────────────
    rows = []
    for name in WATCHED:
        repo = work / name
        if not (repo / ".git").is_dir():
            continue
        found = unpushed(repo)
        if found:
            rows.append((name, *found))
    total_commits = sum(r[2] for r in rows)

    # ── 2. prepared, unsubmitted pull requests ─────────────────────────────
    plan, plan_error = submission_plan()

    print("=" * 72)
    print("HANDOFF STATUS — everything below is local; nothing has been pushed")
    print("=" * 72)
    print()

    print(f"UNPUSHED COMMITS: {total_commits} across {len(rows)} repositor"
          f"{'y' if len(rows) == 1 else 'ies'}")
    missed = unwatched(work)
    if missed:
        print("  NOT IN THE LIST BELOW — their push is invisible until they are added:")
        for name, count in missed:
            print(f"      {name}  ({count} commit(s) ahead)")
    if not rows:
        print("  none — every watched repository is level with its upstream")
    for name, branch, count, subjects in rows:
        print(f"  {name}  ({count} ahead of origin/{branch})")
        for line in subjects[:6]:
            print(f"      {line}")
        if len(subjects) > 6:
            print(f"      ... and {len(subjects) - 6} more")
    print()

    print(f"PREPARED PULL REQUESTS, NOT SUBMITTED: {len(plan)}")
    if plan_error:
        print(f"  {plan_error}")
    for branch, clone, _body, description in plan:
        print(f"  {branch:32} {description}")
    if plan:
        print("  Submit with: python3 "
              "${DSH_HOME:-$HOME/.dsh}/.agent-presets/laya-contributor/tools/"
              "submit_prepared_work.py --execute")
    print()

    prepared = {branch for branch, _clone, _body, _desc in plan}
    others = other_unpushed_branches(work, prepared)
    if others:
        print("UNPUSHED BRANCHES NOT IN THE PREPARED LIST (never pushed, or a fix to your own repo)")
        for name, branch, ahead in others:
            print(f"  {name}/{branch}  ({ahead} commit(s) ahead of origin/main)")
        print()

    print("WAITING ON YOU (from the task ledger: open+high first, then blocked)")
    waiting = waiting_on_you()
    if not waiting:
        print("  none recorded")
    for item in waiting:
        title = item.get("title", "(untitled)")
        print(f"  [{item.get('status', '?'):7} {item.get('priority', 'normal'):6}] {title}")
    print()

    print("VERIFIED STATE (self-tests, run just now)")
    for tool in ("check_laya_home", "verify_claims", "audit_prepared_work",
                 "submit_prepared_work"):
        path = HERE / f"{tool}.py"
        if not path.is_file():
            print(f"  {tool:24} MISSING")
            continue
        code = subprocess.run([sys.executable, str(path), "--self-test"],
                              capture_output=True, text=True).returncode
        print(f"  {tool:24} {'PASS' if code == 0 else 'FAIL'}")
    print()
    print("Neither this script nor anything in this preset pushes, comments, or "
          "opens a pull request. Those are your actions; this only reports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
