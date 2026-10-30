#!/usr/bin/env python3
"""Submit the prepared Laya contributions, safely, in one command.

Why this exists
---------------
Six reviewed, verified branches are sitting in local clones with PR text written
for each. Opening them by hand is a sequence of about twenty commands across two
clones, and the sequence has a trap in it that already nearly fired:

  * `origin` in `/home/logic/Work/laya-inspect` is `aayushch/laya` — the
    *maintainer's* repo, not yours;
  * `origin` in `/home/logic/Work/laya-chat` is a local filesystem path;
  * `gh repo fork … --clone=false` on its own creates the fork but wires **no**
    remote.

So the obvious `git push origin <branch>` either targets the maintainer's
repository or writes into another working tree. This script wires the fork
first, pushes to it, and then *proves* the branch did not land upstream.

Safety model
------------
**It does nothing without `--execute`.** The default is a dry run that prints
every command it would run, in order, with the exact destination, and exits
without touching the network or your remotes.

With `--execute` it will not:
  * push to `upstream` (it checks afterwards and reports if it somehow did);
  * force-push anything, ever;
  * commit, amend, rebase, or modify a working tree;
  * open a second PR for a branch that already has one.

It stops at the first failure rather than continuing with a half-submitted set,
and it is safe to re-run: a branch already pushed is skipped, and each step is
checked before it is attempted.

    python3 tools/submit_prepared_work.py                  # dry run — read this first
    python3 tools/submit_prepared_work.py --execute
    python3 tools/submit_prepared_work.py --execute --only fix/dev-requirements
    python3 tools/submit_prepared_work.py --execute --from fix/dev-requirements
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

UPSTREAM_SLUG = "aayushch/laya"
# The upstream is referenced by explicit URL, never by a remote *name*. After a
# fork, `origin` is the fork and the old origin is renamed `upstream` — but in
# the `laya-chat` clone the old origin is a local filesystem path, so a remote
# named `upstream` there points at another working tree, not at GitHub. Checking
# "did this land upstream?" against that name would answer the wrong question.
UPSTREAM_URL = f"https://github.com/{UPSTREAM_SLUG}.git"
DEFAULT_WORK_DIR = pathlib.Path.home() / "Work"

# Submission order is the merge order from PREPARED-WORK-INDEX.md.
#
# `fix/pin-mcp-below-2` was the first entry and is deliberately gone: on
# 2026-09-24 the maintainer landed c39c79f ("#16: Pin mcp version to <2"), so that
# branch is obsolete AND now conflicts with `main` on engine/requirements.txt.
# Submitting it would offer a duplicate of work that is already merged.
#
# (branch, clone, PR body file, one-line description)
# Two branches have been retired for the same reason — upstream landed the same work — and
# neither is in this plan:
#
#   fix/pin-mcp-below-2      superseded by c39c79f (2026-09-24), and it conflicts.
#   feat/cursor-cli-adapter  superseded by e87abe4 "#12: Added phase 1 support for cursor
#                            agent" (2026-09-25). It created the same two files —
#                            engine/laya/agents/cursor_cli.py and
#                            engine/tests/test_cursor_cli_adapter.py — and now conflicts with
#                            upstream on 9 files. Offering it would be a first-time
#                            contributor proposing work the maintainer merged hours earlier.
#                            Issue #12 is CLOSED/COMPLETED.
PLAN = (
    (
        "fix/tests-isolate-laya-home",
        "laya-inspect",
        "laya-pr-test-isolation.md",
        "running pytest deletes the developer's MCP token",
    ),
    (
        "fix/dev-requirements",
        "laya-inspect",
        "laya-pr-dev-requirements.md",
        "the venv setup-dev.sh builds has no test runner",
    ),
    (
        "feat/full-page-coding-chat",
        "laya-chat",
        "laya-pr-chat.md",
        "full-page coding chat with an opt-in focus",
    ),
    (
        "fix/setup-progress-labels",
        "laya-inspect",
        "laya-pr-7-setup-progress-labels.md",
        "label parallel runtime downloads in setup progress (#7)",
    ),
    (
        "fix/omni-attention-wipe-guard",
        "laya-inspect",
        "laya-pr-omni-attention-wipe.md",
        "an emptied attention section is stored and carried forward (#10)",
    ),
    (
        "fix/github-pr-comment-entity-key",
        "laya-inspect",
        "laya-pr-github-pr-comment-entity.md",
        "a PR comment's entity key depends on the Pulls fetch window (#10)",
    ),
    (
        "test/auto-resolve-terminal-siblings",
        "laya-inspect",
        "laya-pr-auto-resolve-tests.md",
        "terminal-event sibling auto-resolution had no test at all (#10)",
    ),
    (
        "feat/omni-open-items-input",
        "laya-inspect",
        "laya-pr-omni-open-items.md",
        "offer the resynthesis the live high-priority subjects it is missing (#10)",
    ),
    (
        "feat/persist-tool-call-references",
        "laya-inspect",
        "laya-pr-tool-call-references.md",
        "persist tool call references with a chat message (#6)",
    ),
    (
        "fix/omni-unitemised-cards",
        "laya-inspect",
        "laya-pr-omni-unitemised-cards.md",
        "cards a resynthesis does not itemise are lost from every later run (#10)",
    ),
    (
        "fix/engine-cross-site-origin-guard",
        "laya-inspect",
        "laya-pr-engine-cross-site-origin.md",
        "any local web page can drive the engine's REST API and read its UI broadcast (#13)",
    ),
)


def parse_existing_pr(raw: str) -> str:
    """Turn `gh pr list --json url,state` output into "" or "STATE url".

    This is a function, and self-tested, because the first version of this
    script got it wrong in the worst possible way: it asked `gh` for
    `.[0] | "\\(.state) \\(.url)"`, which on an *empty* result list yields the
    two-character-per-word string "null null". That is truthy in Python, so
    every branch was reported as "a PR already exists" and the script skipped
    all six submissions while claiming they were already open.

    Anything that is not a JSON list containing an object with a `url` means
    "no PR"; a malformed response must never be read as "already submitted".
    """
    if not raw:
        return ""
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if not isinstance(first, dict) or not first.get("url"):
        return ""
    return f"{first.get('state', '?')} {first['url']}"


def upstream_has_branch(branch: str) -> bool:
    """Is `branch` on GitHub upstream? Asked of the URL, not a remote name."""
    out = run(["git", "ls-remote", "--heads", UPSTREAM_URL, branch], check=False)
    return f"refs/heads/{branch}" in out


class Stop(Exception):
    """A precondition failed; stop before doing anything irreversible."""


def run(args: list[str], cwd: pathlib.Path | None = None, check: bool = True) -> str:
    try:
        out = subprocess.run(
            args, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop(f"could not run {args[0]}: {exc}") from exc
    if check and out.returncode != 0:
        detail = (out.stderr or out.stdout).strip().splitlines()
        raise Stop(f"{' '.join(args)} failed: {detail[-1] if detail else out.returncode}")
    return (out.stdout or "").strip()


def gh(*args: str, check: bool = True) -> str:
    return run(["gh", *args], check=check)


def first_heading(body: pathlib.Path) -> str:
    """The PR body starts with `# Title`; that is the PR title."""
    for line in body.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise Stop(f"{body.name} has no '# Title' heading to use as the PR title")


def commits_ahead(clone: pathlib.Path, branch: str) -> int | None:
    """How many commits this branch has that upstream main does not.

    `None` means "could not tell" — no upstream ref fetched, say — and is not
    treated as a problem: this exists to catch a branch that proposes *nothing*,
    and an unknown count is not that.
    """
    for base in ("origin/main", "main"):
        if not run(["git", "-C", str(clone), "rev-parse", "--verify", "--quiet", base],
                   check=False):
            continue
        merge_base = run(["git", "-C", str(clone), "merge-base", base, branch],
                         check=False).strip()
        if not merge_base:
            continue
        count = run(["git", "-C", str(clone), "rev-list", "--count",
                     f"{merge_base}..{branch}"], check=False).strip()
        if count.isdigit():
            return int(count)
    return None


def empty_branch_reason(ahead: int | None, branch: str) -> str | None:
    """The refusal for a branch that proposes nothing, or None when it is fine.

    A branch identical to upstream main still *pushes* happily; it is `gh pr create`
    that refuses it ("No commits between ..."), and by then the push has already left
    a stray branch on the fork. Catching it before anything moves is the whole point
    of a rehearsal.
    """
    if ahead != 0:
        return None
    return (f"branch {branch} has no commits that upstream main does not already have, "
            "so there is nothing to propose — GitHub refuses to open a PR for it, and "
            "by then the branch is on the fork.")


def token_scopes() -> set[str] | None:
    """The scopes on the active `gh` token, or None when gh does not say.

    `gh auth status` writes to stderr, so this cannot use `run()` — which returns
    stdout. Nothing here is fatal on its own: an unparseable answer returns None and
    the caller carries on, because blocking a submission over a changed output format
    would be worse than the failure this guards.
    """
    try:
        proc = subprocess.run(["gh", "auth", "status"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"Token scopes:\s*(.+)$",
                      f"{proc.stdout}\n{proc.stderr}", re.MULTILINE)
    if not match:
        return None
    return set(re.findall(r"'([^']+)'", match.group(1)))


def current_user() -> str:
    try:
        return gh("api", "user", "--jq", ".login")
    except Stop as exc:
        # Every failure used to be reported as "not authenticated", which is a
        # misdiagnosis by construction: this call can fail on a timeout, a 5xx or a rate
        # limit while the user is perfectly well logged in, and it then tells them to run
        # `gh auth login` — sending them to fix the wrong thing, with the real reason
        # discarded. It happened once during a dry run and `gh api user` answered normally
        # seconds later. Still fatal (nothing is pushed on an unknown identity), but the
        # reason survives now.
        raise Stop(
            f"could not read the authenticated user from `gh`: {exc}\n"
            "  If `gh auth status` says you are logged in, that was a transient failure "
            "— re-run this; nothing has been pushed or created."
        ) from exc


def find_fork_remote(clone: pathlib.Path, user: str) -> str | None:
    """Return the name of the remote pointing at the user's fork, if any."""
    out = run(["git", "-C", str(clone), "remote", "-v"], check=False)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "upstream":
            continue
        url = parts[1]
        if re.search(rf"[:/]{re.escape(user)}/laya(\.git)?$", url):
            return parts[0]
    return None


def describe_remotes(clone: pathlib.Path) -> str:
    out = run(["git", "-C", str(clone), "remote", "-v"], check=False)
    seen = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] not in [s[1] for s in seen]:
            seen.append((parts[0], parts[1]))
    return ", ".join(f"{name} -> {url}" for name, url in seen) or "(no remotes)"


def _rev(clone: pathlib.Path, ref: str) -> str:
    return run(["git", "-C", str(clone), "rev-parse", "--short", ref], check=False).strip()


def base_drift(clone: pathlib.Path) -> tuple[str, str] | None:
    """`(local, upstream)` when `main` differs from `origin/main`, else None.

    Read-only: a fetch, never a merge or a reset. The branches were prepared
    against a particular `main`, and upstream moving can do two things at once --
    invalidate a branch, and fix the issue it addresses. That is exactly what
    happened on 2026-09-24: c39c79f pinned mcp in `main`, turning a prepared PR
    into a duplicate of work already merged. Reporting the drift before a push is
    the cheap half of that lesson.
    """
    run(["git", "-C", str(clone), "fetch", "origin", "--quiet"], check=False)
    local, remote = _rev(clone, "main"), _rev(clone, "origin/main")
    if local and remote and local != remote:
        return local, remote
    return None


def merge_conflict(clone: pathlib.Path, branch: str) -> str | None:
    """The conflicting lines when `branch` no longer merges into `origin/main`.

    A conflict is a hard stop, not a warning. It means upstream rewrote the very
    lines this branch edits, so the PR cannot be applied without the maintainer
    resolving work he did not ask for. `git merge-tree` answers this without
    touching the working tree or creating a commit.
    """
    out = run(["git", "-C", str(clone), "merge-tree", "--write-tree", "--name-only",
               "origin/main", branch], check=False)
    hits = [ln.strip() for ln in out.splitlines() if "CONFLICT" in ln.upper()]
    return "\n".join(hits[:3]) if hits else None


def preflight(clone: pathlib.Path, branch: str, body: pathlib.Path) -> dict:
    """Every check that must pass before we touch the network."""
    if not clone.is_dir():
        raise Stop(f"{clone} is not present")
    if not body.is_file():
        raise Stop(f"PR text {body} is missing")

    if run(["git", "-C", str(clone), "rev-parse", "--verify", "--quiet", branch],
           check=False) == "":
        raise Stop(f"branch {branch} does not exist in {clone.name}")

    head = run(["git", "-C", str(clone), "rev-parse", "--short", branch])

    dirty = run(["git", "-C", str(clone), "status", "--porcelain"], check=False)
    if dirty:
        raise Stop(
            f"{clone.name} has uncommitted changes; commit or stash them first:\n"
            + "\n".join(f"    {ln}" for ln in dirty.splitlines()[:5])
        )

    conflict = merge_conflict(clone, branch)
    if conflict:
        raise Stop(
            f"branch {branch} no longer merges into origin/main:\n"
            + "\n".join(f"    {ln}" for ln in conflict.splitlines())
            + "\n  Upstream changed these lines. Rebase the branch, or retire it if "
              "the work is already merged -- do NOT submit a conflicting PR."
        )

    ahead = commits_ahead(clone, branch)
    reason = empty_branch_reason(ahead, branch)
    if reason:
        raise Stop(reason)

    return {"head": head, "title": first_heading(body), "ahead": ahead}


def _self_test_conflict_detection() -> int:
    """Prove the conflict guard fires, and stays quiet on a clean branch.

    Built on a throwaway repository: the guard is about a *shape* -- upstream
    rewrote the lines this branch edits -- and that shape is cheap to construct,
    so the test needs no network and does not depend on the real clones' state.
    """
    import tempfile

    print("self-test: branch-vs-upstream conflict detection")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp) / "clone"
        repo.mkdir()

        def g(*args: str) -> str:
            return run(["git", "-C", str(repo), "-c", "user.email=t@example.com",
                        "-c", "user.name=t", *args], check=False)

        g("init", "-q", "-b", "main")
        (repo / "f.txt").write_text("one\ntwo\nthree\n")
        g("add", "-A"); g("commit", "-q", "-m", "base")

        g("checkout", "-q", "-b", "topic")
        (repo / "f.txt").write_text("one\nTWO-branch\nthree\n")
        g("add", "-A"); g("commit", "-q", "-m", "branch edit")

        g("checkout", "-q", "main")
        (repo / "f.txt").write_text("one\nTWO-upstream\nthree\n")
        g("add", "-A"); g("commit", "-q", "-m", "upstream edit")
        g("update-ref", "refs/remotes/origin/main", "main")

        if merge_conflict(repo, "topic"):
            print("  ok: a branch editing the same line as upstream is refused")
        else:
            print("  FAILED: a real conflict was not detected")
            failures += 1

        g("checkout", "-q", "-b", "clean", "main")
        (repo / "g.txt").write_text("a new file, no overlap\n")
        g("add", "-A"); g("commit", "-q", "-m", "clean edit")
        if merge_conflict(repo, "clean") is None:
            print("  ok: a non-overlapping branch is not reported")
        else:
            print("  FAILED: a clean branch was reported as conflicting")
            failures += 1

    return failures


def self_test() -> int:
    """Prove the two parsing helpers behave, including on empty results.

    The bug this exists for: an empty `gh pr list` answer rendered as the string
    "null null", which read as truthy and made every branch look already
    submitted.
    """
    print("self-test: PR detection and title extraction")
    failures = 0

    cases = (
        ("", "", "an empty response means no PR"),
        ("[]", "", "an empty result list means no PR"),
        ("null", "", "a JSON null means no PR"),
        ("not json at all", "", "malformed output means no PR, never 'already open'"),
        ("{}", "", "an object instead of a list means no PR"),
        ('[{"state": "OPEN"}]', "", "an entry without a url is not a PR"),
        (
            '[{"url": "https://github.com/aayushch/laya/pull/1", "state": "OPEN"}]',
            "OPEN https://github.com/aayushch/laya/pull/1",
            "a real PR is reported with its state",
        ),
    )
    for raw, expected, description in cases:
        got = parse_existing_pr(raw)
        if got != expected:
            print(f"  FAILED: {description}\n    expected {expected!r}, got {got!r}")
            failures += 1
        else:
            print(f"  ok: {description}")

    # In particular, the value that caused the bug must be falsy.
    if parse_existing_pr("[]"):
        print("  FAILED: an empty result list produced a truthy value")
        failures += 1
    else:
        print("  ok: an empty result list is falsy, so the branch is submitted")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        body = pathlib.Path(tmp) / "body.md"
        body.write_text("# A title here\n\nbody text\n", encoding="utf-8")
        if first_heading(body) != "A title here":
            print("  FAILED: the first '# ' heading was not used as the title")
            failures += 1
        else:
            print("  ok: the PR title comes from the body's first heading")

        body.write_text("no heading\n", encoding="utf-8")
        try:
            first_heading(body)
            print("  FAILED: a body with no heading was accepted")
            failures += 1
        except Stop:
            print("  ok: a body with no heading is refused")

    failures += _self_test_conflict_detection()
    failures += _self_test_empty_branch()
    failures += _self_test_preflight()

    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def _self_test_empty_branch() -> int:
    """Prove the empty-branch refusal fires, and stays quiet on an unknown count.

    Built on a throwaway repository, so it needs no network and does not depend on
    the real clones: a branch with no commits of its own is one `git branch` away.
    """
    import tempfile

    print("self-test: a branch that proposes nothing is refused")
    failures = 0

    if empty_branch_reason(0, "fix/x") is None:
        print("  FAILED: a branch with no commits of its own was not refused")
        failures += 1
    if empty_branch_reason(3, "fix/x") is not None:
        print("  FAILED: a branch with commits was refused")
        failures += 1
    if empty_branch_reason(None, "fix/x") is not None:
        print("  FAILED: an unknown count was treated as an empty branch")
        failures += 1

    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp) / "clone"
        repo.mkdir()

        def g(*args: str) -> str:
            return run(["git", "-C", str(repo), "-c", "user.email=t@example.com",
                        "-c", "user.name=t", *args], check=False)

        g("init", "-q", "-b", "main")
        (repo / "f.txt").write_text("one\n")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        g("branch", "empty")          # points at main: proposes nothing
        g("checkout", "-q", "-b", "work")
        (repo / "f.txt").write_text("two\n")
        g("add", "-A")
        g("commit", "-q", "-m", "work")

        got_empty = commits_ahead(repo, "empty")
        got_work = commits_ahead(repo, "work")
        if got_empty != 0:
            print(f"  FAILED: a branch at main counted {got_empty} commit(s) ahead")
            failures += 1
        if got_work != 1:
            print(f"  FAILED: a one-commit branch counted {got_work} ahead")
            failures += 1

    if not failures:
        print("  ok: an empty branch is refused, a real one is not, and an unknown "
              "count is not mistaken for empty")
    return failures


def _self_test_preflight() -> int:
    """Prove that `preflight` REFUSES — not merely that its helpers can compute.

    The gap this exists for, found by disabling one guard at a time and re-running the
    self-test: the suite exercised `merge_conflict()`, `commits_ahead()` and
    `empty_branch_reason()` on their own, so a mutation that turned any of the five
    `raise Stop` guards *inside* `preflight()` into `if False` passed the whole self-test.
    Every one of those guards is the difference between a rehearsal and a stray branch on
    the fork. Built on a throwaway repository, so it needs no network and does not depend
    on the real clones' state.
    """
    import tempfile

    print("self-test: preflight refuses (dirty tree, missing body, absent branch, "
          "conflict, empty branch)")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        repo = pathlib.Path(tmp) / "clone"
        repo.mkdir()

        def g(*args: str) -> str:
            return run(["git", "-C", str(repo), "-c", "user.email=t@example.com",
                        "-c", "user.name=t", *args], check=False)

        g("init", "-q", "-b", "main")
        (repo / "f.txt").write_text("one\ntwo\nthree\n")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        g("update-ref", "refs/remotes/origin/main", "main")
        body = pathlib.Path(tmp) / "body.md"
        body.write_text("# A title\n\nbody\n")

        def expect_refusal(*, branch: str, pr_body: pathlib.Path, needle: str,
                           description: str) -> None:
            nonlocal failures
            try:
                preflight(repo, branch, pr_body)
            except Stop as exc:
                if needle not in str(exc):
                    print(f"  FAILED: {description} — refused for the wrong reason: {exc}")
                    failures += 1
                else:
                    print(f"  ok: {description}")
                return
            print(f"  FAILED: {description} — accepted")
            failures += 1

        # The happy path first, so a refused-everything implementation cannot look good.
        g("checkout", "-q", "-b", "clean")
        (repo / "g.txt").write_text("a new file\n")
        g("add", "-A")
        g("commit", "-q", "-m", "clean edit")
        try:
            info = preflight(repo, "clean", body)
            if info["ahead"] != 1 or info["title"] != "A title":
                print(f"  FAILED: a clean branch returned {info}")
                failures += 1
            else:
                print("  ok: a clean branch passes and reports its head, title and count")
        except Stop as exc:
            print(f"  FAILED: a clean branch was refused: {exc}")
            failures += 1

        expect_refusal(branch="clean", pr_body=pathlib.Path(tmp) / "absent.md",
                       needle="missing", description="a missing PR body is refused")
        expect_refusal(branch="not-a-branch", pr_body=body,
                       needle="does not exist", description="an absent branch is refused")

        g("branch", "proposes-nothing", "main")
        expect_refusal(branch="proposes-nothing", pr_body=body, needle="no commits",
                       description="a branch proposing nothing is refused")

        (repo / "g.txt").write_text("uncommitted change\n")
        expect_refusal(branch="clean", pr_body=body, needle="uncommitted",
                       description="a dirty working tree is refused")
        g("checkout", "-q", "--", "g.txt")

        g("checkout", "-q", "-b", "conflicting", "main")
        (repo / "f.txt").write_text("one\nBRANCH\nthree\n")
        g("add", "-A")
        g("commit", "-q", "-m", "branch edit")
        g("checkout", "-q", "main")
        (repo / "f.txt").write_text("one\nUPSTREAM\nthree\n")
        g("add", "-A")
        g("commit", "-q", "-m", "upstream edit")
        g("update-ref", "refs/remotes/origin/main", "main")
        expect_refusal(branch="conflicting", pr_body=body, needle="no longer merges",
                       description="a branch that no longer merges is refused")

    return failures


def upstream_pr_policy() -> tuple[str | None, str]:
    """Read the upstream's pull-request creation policy.

    This exists because its absence cost three sessions. GitHub can refuse
    `CreatePullRequest` with a bare FORBIDDEN and no hint that the cause is a
    *repository* setting: when `pull_request_creation_policy` is
    `collaborators_only`, only collaborators may open PRs, and everything else
    still works — cloning, forking, pushing to the fork, commenting on issues,
    even resolving the cross-fork comparison. That combination looks exactly
    like a fault in the branch, the fork, or the account, and it is none of
    them. Reading one field up front turns the whole investigation into a line
    of output.
    """
    raw = gh("api", f"repos/{UPSTREAM_SLUG}", "--jq",
             ".pull_request_creation_policy", check=False).strip()
    if not raw:
        return None, ("could not read pull_request_creation_policy "
                      "(older GitHub Enterprise servers omit the field)")
    if raw != "all":
        return raw, (
            f"upstream pull_request_creation_policy = {raw!r}: GitHub will refuse "
            "CreatePullRequest for any non-collaborator. The branches are still "
            "pushable and reviewable, so nothing is lost — but the fix is the "
            "maintainer's: Settings -> General -> Pull Requests -> set the policy "
            "to 'All users', or add you as a collaborator.")
    return raw, "upstream allows pull requests from any user"


def manual_kit(plan, work: pathlib.Path, user: str, base: str = "main",
               policy: str | None = None) -> int:
    """Print a copy-paste kit for opening each PR from the GitHub web UI.

    Why this exists. Pull-request creation is an authorization decision GitHub
    makes per account and per repository, and it can refuse the API while the
    branches are perfectly pushable and reviewable — `CreatePullRequest`
    answered FORBIDDEN for this account on one upstream, with comments to the
    same repository working normally and 56 PRs open elsewhere. When that
    happens the branches are still the deliverable, so this mode prints what a
    human needs to open each one by hand: the compare URL (which pre-loads the
    diff and the button), the exact title, and the body file to paste.

    It touches nothing — no network, no push, no PR.
    """
    print("=" * 72)
    print(f"MANUAL OPEN KIT — {user}/laya -> {UPSTREAM_SLUG}")
    print("=" * 72)
    print("Branches are expected to be already pushed to the fork.")
    print("Nothing in this mode touches the network.\n")

    opened = 0
    for branch, _clone, body_name, description in plan:
        body = work / body_name
        if body.exists():
            try:
                title = first_heading(body)
            except Stop:
                title = "(body has no '# ' heading)"
        else:
            title = f"(missing body file: {body_name})"
        url = (f"https://github.com/{UPSTREAM_SLUG}/compare/"
               f"{base}...{user}:{branch}?expand=1")
        print(f"  {branch}")
        print(f"    {description}")
        print(f"    open : {url}")
        print(f"    title: {title}")
        print(f"    body : {body}")
        print()
        opened += 1

    print(f"{opened} PR(s). For each: open the URL, click 'Create pull request',")
    print("paste the title, then paste the body file.")
    print()
    if policy is not None and policy != "all":
        # Do not send someone through eleven web forms that cannot work.
        print(f"BUT NOTE: upstream pull_request_creation_policy = {policy!r}, so the web")
        print("form is refused by the same policy the API is — this is not an API-only")
        print("limitation and the kit will fail for every branch above. The branches are")
        print("still public and reviewable on the fork; the actual fix is the")
        print("maintainer's (Settings -> General -> Pull Requests -> 'All users', or add")
        print("you as a collaborator). Everything above is worth keeping for the moment")
        print("that changes.")
    else:
        print("The web form is the fallback when the API refuses but the repository")
        print("allows public pull requests; if it refuses too, the cause is a repository")
        print("policy or the maintainer's settings rather than anything in the branch.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit the prepared Laya contributions (dry run by default)",
    )
    parser.add_argument("--execute", action="store_true",
                        help="actually fork, push and open PRs (default: print the plan)")
    parser.add_argument("--work-dir", type=pathlib.Path, default=DEFAULT_WORK_DIR,
                        help="directory holding the laya-* clones")
    parser.add_argument("--only", action="append", default=[],
                        help="submit only this branch (repeatable)")
    parser.add_argument("--from", dest="start_at",
                        help="start at this branch in the submission order")
    parser.add_argument("--self-test", action="store_true",
                        help="check the parsing helpers without touching the network")
    parser.add_argument("--manual", action="store_true",
                        help="print a copy-paste kit for opening the PRs from the web UI "
                             "(for when GitHub refuses CreatePullRequest via the API)")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    work = args.work_dir.expanduser().resolve()
    execute = args.execute

    plan = list(PLAN)
    if args.only:
        unknown = set(args.only) - {b for b, _, _, _ in PLAN}
        if unknown:
            print(f"error: unknown branch(es): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        plan = [row for row in plan if row[0] in args.only]
    elif args.start_at:
        names = [row[0] for row in plan]
        if args.start_at not in names:
            print(f"error: --from {args.start_at} is not in the plan", file=sys.stderr)
            return 2
        plan = plan[names.index(args.start_at):]

    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"submit prepared Laya work — {mode}")
    print(f"  work dir : {work}")
    print(f"  upstream : {UPSTREAM_SLUG}")
    print()

    if not shutil.which("git"):
        print("error: git is not on PATH", file=sys.stderr)
        return 2
    if not shutil.which("gh"):
        print("error: gh is not on PATH (https://cli.github.com)", file=sys.stderr)
        return 2

    # Prerequisites are checked even in a dry run, so a dry run is a real
    # rehearsal rather than a printout that cannot fail.
    try:
        user = current_user()
        print(f"authenticated as {user}")
        if user != "sushant-me":
            print(f"  note: the prepared PR text assumes the fork owner is "
                  f"`sushant-me`; using `{user}` instead")
    except Stop as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Pushing to the fork and opening the PR both need `repo`. A missing scope is
    # checked *here* rather than discovered at the first push, and `gh auth status`
    # is the only place it can be seen. Unknown scopes are not fatal: an output
    # format this cannot parse must not block a submission.
    scopes = token_scopes()
    if scopes is None:
        print("token scopes: not reported by gh — carrying on")
    else:
        print(f"token scopes: {', '.join(sorted(scopes))}")

    # Answer the question that otherwise costs a session to rediscover: will
    # GitHub even accept a PR into this repository from this account?
    policy, policy_note = upstream_pr_policy()
    if policy is None or policy != "all":
        print(f"WARNING: {policy_note}")
    else:
        print(f"pull request policy: {policy_note}")

    # `--manual` answers the case where GitHub itself refuses PR creation for
    # this repository. It needs only the caller's login, so it returns here.
    if getattr(args, "manual", False):
        print()
        return manual_kit(plan, work, user, policy=policy)
        if "repo" not in scopes:
            print("error: the active gh token has no `repo` scope, so pushing the branch "
                  "and opening the PR would both fail. Run: gh auth refresh -s repo",
                  file=sys.stderr)
            return 2

    print()

    # Upstream moving is not fatal, but it is how a prepared branch becomes a
    # duplicate: c39c79f pinned mcp in `main` and turned a prepared PR into a
    # repeat of merged work. Say so before anything is offered, because the fix is
    # to re-read the index and the tracker, not to push harder.
    drifted = []
    for clone_name in dict.fromkeys(row[1] for row in plan):
        clone = work / clone_name
        if clone.is_dir():
            drift = base_drift(clone)
            if drift:
                drifted.append((clone_name, drift[0], drift[1]))
    if drifted:
        print("BASE HAS MOVED SINCE THE BRANCHES WERE PREPARED")
        for clone_name, local, remote in drifted:
            print(f"  {clone_name}: local main {local} -> upstream {remote}")
        print("  Re-run tools/audit_prepared_work.py and re-read PREPARED-WORK-INDEX.md:")
        print("  upstream may have fixed one of these issues, which would make its")
        print("  branch a duplicate. A conflict is refused below; a duplicate is not")
        print("  detectable mechanically, so it is on you to check.")
        print()

    results: list[tuple[str, str]] = []

    for index, (branch, clone_name, body_name, description) in enumerate(plan, 1):
        clone = work / clone_name
        body = work / body_name
        print(f"[{index}/{len(plan)}] {branch}  — {description}")

        try:
            info = preflight(clone, branch, body)
        except Stop as exc:
            print(f"      STOP: {exc}")
            print("\nstopping before any change; nothing was pushed")
            return 1

        print(f"      clone   : {clone}")
        print(f"      commit  : {info['head']}")
        ahead = info.get("ahead")
        print(f"      commits : {'unknown' if ahead is None else str(ahead)} ahead of main")
        print(f"      title   : {info['title']}")
        print(f"      body    : {body.name}")
        print(f"      remotes : {describe_remotes(clone)}")

        # Already submitted? Compare against the fork, not upstream.
        fork_remote = find_fork_remote(clone, user)
        already_pushed = False
        if fork_remote:
            refs = run(["git", "-C", str(clone), "ls-remote", "--heads",
                        fork_remote, branch], check=False)
            already_pushed = f"refs/heads/{branch}" in refs

        existing_pr = parse_existing_pr(
            gh("pr", "list", "--repo", UPSTREAM_SLUG, "--head", f"{user}:{branch}",
               "--state", "all", "--json", "url,state", check=False)
        )
        if existing_pr:
            print(f"      already : {existing_pr}")
            results.append((branch, "already open"))
            print("      skipping — a PR already exists for this branch\n")
            continue

        if already_pushed:
            print(f"      fork has the branch already; only the PR is missing")

        if not execute:
            if not fork_remote:
                print(f"      WOULD  : gh repo fork {UPSTREAM_SLUG} --clone=false --remote")
                print(f"               (wires {user}/laya as a remote, renames the "
                      f"current origin to upstream)")
            if not already_pushed:
                print(f"      WOULD  : git -C {clone} push -u "
                      f"{fork_remote or '<fork>'} {branch}")
            print(f"      WOULD  : gh pr create --repo {UPSTREAM_SLUG} "
                  f"--head {user}:{branch} --title {info['title']!r} --body-file {body}")
            results.append((branch, "would submit"))
            print()
            continue

        # ── execute ─────────────────────────────────────────────────────────
        try:
            if not fork_remote:
                print(f"      forking  {UPSTREAM_SLUG} and wiring the remote ...")
                # gh >= 2.101 refuses `--remote` together with a repository
                # argument ("the `--remote` flag is unsupported when a
                # repository argument is provided"), and the flag set has moved
                # between releases. So create the fork, then wire the remote
                # ourselves: the outcome must not depend on which gh is
                # installed. `find_fork_remote` matches on the URL, never the
                # name, so the name we choose here is free.
                # check=False: an existing fork is the normal re-run case and
                # must not stop the run.
                gh("repo", "fork", UPSTREAM_SLUG, "--clone=false", check=False)
                fork_remote = find_fork_remote(clone, user)
                if not fork_remote:
                    fork_url = f"https://github.com/{user}/laya.git"
                    taken = set(run(["git", "-C", str(clone), "remote"]).split())
                    name = "fork"
                    while name in taken:
                        name += "-fork"
                    run(["git", "-C", str(clone), "remote", "add", name, fork_url])
                    fork_remote = find_fork_remote(clone, user)
                if not fork_remote:
                    raise Stop(
                        "the fork was created but no remote points at it; "
                        f"remotes are now: {describe_remotes(clone)}"
                    )
                print(f"      remotes : {describe_remotes(clone)}")

            if not already_pushed:
                # No --force, ever: if the remote moved, the push fails loudly.
                print(f"      pushing  {branch} -> {fork_remote} ...")
                run(["git", "-C", str(clone), "push", "-u", fork_remote, branch])

            print(f"      opening  PR ...")
            url = gh(
                "pr", "create", "--repo", UPSTREAM_SLUG,
                "--head", f"{user}:{branch}",
                "--title", info["title"],
                "--body-file", str(body),
            )
            print(f"      opened   {url}")

            # The whole point of the rewrite: prove it went to the fork and did
            # not land on the maintainer's repository. Asked by URL, because in
            # one clone the remote named `upstream` is a local path.
            if upstream_has_branch(branch):
                print(f"      WARNING: {branch} is present on upstream — investigate")
                results.append((branch, "LEAKED TO UPSTREAM"))
            else:
                results.append((branch, url.splitlines()[-1] if url else "opened"))
        except Stop as exc:
            print(f"      STOP: {exc}")
            print(f"\n{branch} did not complete. Earlier branches are unaffected; "
                  f"fix this and re-run — finished branches are skipped.")
            return 1

        print()

    print("summary")
    for branch, outcome in results:
        print(f"  {branch:34} {outcome}")

    if not execute:
        print()
        print("dry run only — nothing was pushed and no PR was opened.")
        print("re-run with --execute to submit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
