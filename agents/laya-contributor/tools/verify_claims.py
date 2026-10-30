#!/usr/bin/env python3
"""Check the `laya` skill's factual claims against the repository they describe.

Why this exists
---------------
The `laya` skill states things that are true of a *specific* commit: that the
entrypoint is `engine/laya/main.py`, that `main.py` holds 25 `include_router`
calls drawn from 21 `*_api.py` modules, that `mcp` is still unbounded, that the
test suite still lacks the HOME redirect, that five branches are prepared and
unpushed. Every one of those can become false without anyone editing the skill:

  * the maintainer fixes `requirements.txt` and "verified defect #1" is no
    longer a defect, so the agent argues for a bound that already shipped;
  * a refactor moves or splits `main.py` and the count drifts;
  * a branch gets pushed, and "deliberately not pushed" turns a safe rule into
    a false statement about the remote.

This is not hypothetical. Two claims in the skill were already wrong when this
script was written: it named `engine/laya/api/main.py` — a path that has never
existed in any commit, the entrypoint is `engine/laya/main.py` — and it told the
reader to push the chat branch "from `laya-chat`", a clone whose `origin` is a
local filesystem path and therefore cannot reach GitHub at all. Both were found
by hand. A document nobody checks is a document that is eventually wrong.

What it does
------------
Verifies each claim by reading the artefact the claim is about, and reports one
of three states per claim — it does not guess, and it does not treat "could not
check" as a pass:

  PASS     the artefact matches the claim.
  FAIL     the artefact contradicts the claim. Exit code 1.
  UNKNOWN  it could not be checked (missing checkout, no network, no `gh`).
           Reported separately and never counted as a pass.

Defect claims are checks in the *other* direction: "this defect is still live"
passes only while the defect is still present. When the maintainer fixes one,
this script goes red on purpose — that is the signal to update the skill, not a
bug in the script.

    python3 tools/verify_claims.py                    # check the default trees
    python3 tools/verify_claims.py --repo /path/to/laya-inspect
    python3 tools/verify_claims.py --offline          # skip the `gh` / remote checks
    python3 tools/verify_claims.py --self-test        # prove the checks can fail
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys
import tempfile

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# The numbers the skill asserts, and the files they are asserted about. Kept
# literal on purpose: if upstream changes them, this check fails and the skill
# gets corrected, which is the entire point.
EXPECTED_INCLUDE_ROUTER = 25
EXPECTED_API_MODULES = 21

# Repo-relative paths the skill names. Each must exist for the sentence naming
# it to be true.
REQUIRED_PATHS = (
    "engine/laya/main.py",  # the app entrypoint — NOT engine/laya/api/main.py
    "engine/laya/api",
    "engine/laya/pipeline",
    "engine/laya/egress/platforms",
    "engine/laya/models/workspace.py",
    "engine/laya/config.py",
    "engine/laya/agents/base.py",
    "engine/laya/agents/session_manager.py",
    "engine/laya/mcp",
    "engine/laya/llm/prompts",
    "engine/laya/db/migrations",
    "engine/requirements.txt",
    "engine/tests/conftest.py",
    "ui/src/lib/config.ts",
    "CLAUDE.md",
)

# Prepared branches and the clone each one lives in. The skill's table must
# agree with this, and the checker asserts the branches actually exist.
PREPARED_BRANCHES = {
    "laya-inspect": (
        "fix/pin-mcp-below-2",
        "fix/tests-isolate-laya-home",
        "feat/cursor-cli-adapter",
        "fix/setup-progress-labels",
        "fix/dev-requirements",
    ),
    "laya-chat": ("feat/full-page-coding-chat",),
}

# Issue states the skill relies on. `gh` is consulted when available.
#
# 2026-09-25: #16 and #12 both went CLOSED/COMPLETED while this work sat ready. The
# maintainer fixed the mcp pin in c39c79f and then implemented the Cursor adapter himself in
# e87abe4 ("#12: Added phase 1 support for cursor agent"), which created the same two files
# the prepared branch did. That branch is retired; the skill says so. The map is what the
# skill *depends on*, so a CLOSED issue is now the expectation rather than a failure — which
# is precisely how this check found it: it went red the moment upstream finished the work,
# instead of the branch being offered as a duplicate.
EXPECTED_ISSUES = {
    15: "CLOSED",
    16: "CLOSED",
    12: "CLOSED",
    13: "OPEN",
    7: "OPEN",
}


def issue_ref_pattern(number: int) -> "re.Pattern[str]":
    """`#7` as an issue reference — not a substring of `#795`, `#17` or `#70`.

    Boundaries are explicit because the first version of the drift check below
    used a plain substring search and "found" #7 in a commit about the daily
    summary, whose message quotes `"Review PR #795"`. A guard that fires on the
    wrong commit is worse than no guard: a reader learns to ignore it. The
    lookarounds also keep `#17` from matching `#7`, and `#7` inside a word
    (`x#7`) from matching at all.
    """
    return re.compile(rf"(?<![0-9A-Za-z_])#{number}(?![0-9])")


def plan_issues(work: pathlib.Path) -> dict[int, list[str]]:
    """The issue numbers the submission plan references, and by which branches.

    Read out of the plan rather than kept as a second hand-maintained list: a new
    branch cannot then quietly omit the issue it claims to fix. `PLAN` entries are
    `(branch, clone, pr_text, description)` and the issue is written into the
    description, which is where this gets it.
    """
    plan_path = pathlib.Path(__file__).resolve().parent / "submit_prepared_work.py"
    spec = importlib.util.spec_from_file_location("_spw_for_issues", plan_path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found: dict[int, list[str]] = {}
    for branch, _clone, _pr, description in module.PLAN:
        for raw in re.findall(r"#(\d+)", description):
            found.setdefault(int(raw), []).append(branch)
    return found


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.rows.append((name, status, detail))

    @property
    def failed(self) -> int:
        return sum(1 for _, s, _ in self.rows if s == FAIL)

    @property
    def unknown(self) -> int:
        return sum(1 for _, s, _ in self.rows if s == UNKNOWN)

    def render(self) -> None:
        width = max((len(n) for n, _, _ in self.rows), default=0)
        for name, status, detail in self.rows:
            marker = {PASS: "ok  ", FAIL: "FAIL", UNKNOWN: "?   "}[status]
            line = f"  [{marker}] {name.ljust(width)}"
            if detail:
                line += f"  {detail}"
            print(line)


def _read(path: pathlib.Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ── claim groups ────────────────────────────────────────────────────────────


def check_paths(repo: pathlib.Path, rep: Report) -> None:
    """Every repo-relative path the skill names must exist."""
    for rel in REQUIRED_PATHS:
        if (repo / rel).exists():
            rep.add(f"path {rel}", PASS)
        else:
            rep.add(f"path {rel}", FAIL, "named in the skill but does not exist")


def claim_text(repo: pathlib.Path, rel: str) -> str | None:
    """Read `rel` from upstream `main`, falling back to the working tree.

    These checks ask whether a defect is still unfixed *in the project*, and the
    project's truth is `main`. Reading the working tree answers a different
    question: this clone sits on an old feature branch, so the mcp check reported
    the defect as live after the maintainer had already pinned it in c39c79f
    ("#16: Pin mcp version to <2"). A claim checker that inspects whatever happens
    to be checked out is checking the wrong thing, and that near-miss is why this
    function exists.
    """
    code, _ = _git(repo, "rev-parse", "--verify", "--quiet", "main")
    if code == 0:
        code, out = _git(repo, "show", f"main:{rel}")
        if code == 0:
            return out
    return _read(repo / rel)


def check_counts(repo: pathlib.Path, rep: Report) -> None:
    """The skill asserts specific counts; count them again."""
    text = claim_text(repo, "engine/laya/main.py")
    if text is None:
        rep.add("count include_router", UNKNOWN, "engine/laya/main.py unreadable")
    else:
        found = len(re.findall(r"include_router\(", text))
        status = PASS if found == EXPECTED_INCLUDE_ROUTER else FAIL
        rep.add(
            "count include_router",
            status,
            f"{found} in engine/laya/main.py (skill says {EXPECTED_INCLUDE_ROUTER})",
        )

    code, listing = _git(repo, "ls-tree", "--name-only", "main:engine/laya/api")
    api_dir = repo / "engine/laya/api"
    if code == 0 and listing:
        found = len([ln for ln in listing.splitlines() if ln.endswith("_api.py")])
    elif not api_dir.is_dir():
        rep.add("count *_api.py", UNKNOWN, "engine/laya/api missing")
        found = None
    else:
        found = len(list(api_dir.glob("*_api.py")))
    if found is not None:
        status = PASS if found == EXPECTED_API_MODULES else FAIL
        rep.add(
            "count *_api.py",
            status,
            f"{found} modules (skill says {EXPECTED_API_MODULES})",
        )


# Repo-relative file paths named inside the skill are extracted and checked
# against the checkout, because the defect that motivated this script was a path
# the skill *named* and the repository did not have. Only extension-bearing
# paths under a known top-level root are considered; that keeps bare module
# names (`cards_common`), method references (`db/sqlite.transaction()`), and
# home-relative paths (`~/.laya/settings.json`) out of the comparison, so a
# rewording cannot manufacture a failure.
REPO_ROOTS = ("engine", "ui", "scripts", "n8n", "docs", "landing", "marketing")
_BACKTICKED = re.compile(r"`([^`\n]+)`")
_HAS_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,6}$")


def _branch_holding(repo: pathlib.Path, candidate: str) -> str | None:
    """The first local or remote branch whose tree contains `candidate`, if any.

    The skill documents PREPARED work — `engine/requirements-dev.txt` is named in it
    precisely because the branch that adds it is waiting to be submitted. Testing only the
    working tree made this check's verdict depend on which branch the clone happened to be
    sitting on: off `fix/dev-requirements` the path is absent there and the skill reads as
    contradicting the repository. It surfaced only when this session moved the clone off
    that branch for the first time in a while. Existing on a branch is the fact that makes
    the sentence true, and naming WHICH branch is more useful than a bare pass.
    """
    code, refs = _git(repo, "for-each-ref", "--format=%(refname:short)",
                      "refs/heads", "refs/remotes/origin")
    if code != 0:
        return None
    for ref in refs.splitlines():
        ref = ref.strip()
        if not ref or ref.endswith("/HEAD"):
            continue
        if _git(repo, "cat-file", "-e", f"{ref}:{candidate}")[0] == 0:
            return ref
    return None


def check_skill_paths(skill_path: pathlib.Path, repo: pathlib.Path, rep: Report) -> None:
    """Every repo-relative file path the skill names must exist — here or on a branch."""
    text = _read(skill_path)
    if text is None:
        rep.add("skill: named paths", UNKNOWN, f"{skill_path} unreadable")
        return

    checked = 0
    for span in _BACKTICKED.findall(text):
        candidate = span.strip().rstrip(".,;:")
        if candidate.startswith(("~", "/", "$", "*")) or "(" in candidate:
            continue
        if "/" not in candidate or candidate.split("/")[0] not in REPO_ROOTS:
            continue
        if not _HAS_EXTENSION.search(candidate):
            continue
        checked += 1
        if (repo / candidate).exists():
            rep.add(f"skill path {candidate}", PASS)
        elif (branch := _branch_holding(repo, candidate)) is not None:
            rep.add(f"skill path {candidate}", PASS, f"on {branch}")
        else:
            rep.add(
                f"skill path {candidate}",
                FAIL,
                "named in SKILL.md but not in the repository or on any branch",
            )

    if not checked:
        rep.add(
            "skill: named paths",
            UNKNOWN,
            "no repo-relative file paths found — has the skill been reworded?",
        )


PLATFORM_INIT = "engine/laya/egress/platforms/__init__.py"


def _platform_imports(text: str) -> set[str]:
    match = re.search(r"from laya\.egress\.platforms import \(([^)]*)\)", text, re.S)
    if not match:
        return set()
    return {
        name.strip().rstrip(",")
        for name in match.group(1).split()
        if name.strip().rstrip(",")
    }


def _platform_registered(text: str) -> set[str]:
    match = re.search(r"_REGISTRY[^{]*\{(.*?)\n\}", text, re.S)
    if not match:
        return set()
    return set(re.findall(r'"\s*[a-z_]+"\s*:\s*([a-z_]+)\.', match.group(1)))


def check_platform_registration(repo: pathlib.Path, rep: Report) -> None:
    """Every egress adapter module must actually be in `_REGISTRY`.

    There is no central table of adapters *behaviour* by design — each platform
    owns its own contract. There is still a `_REGISTRY` map, and an adapter
    module that exposes `PLATFORM` yet is missing from it is dead code: the
    platform silently never resolves. That is the failure CLAUDE.md's "adding a
    platform is one file" summary invites, because registering it is a second
    file's worth of edits.
    """
    text = _read(repo / PLATFORM_INIT)
    if text is None:
        rep.add("egress: adapters registered", UNKNOWN, f"{PLATFORM_INIT} unreadable")
        return

    imported = _platform_imports(text)
    registered = _platform_registered(text)
    if not imported or not registered:
        rep.add("egress: adapters registered", UNKNOWN,
                "could not parse both the import list and _REGISTRY")
        return

    missing = sorted(imported - registered)
    rep.add(
        "egress: adapters registered",
        FAIL if missing else PASS,
        f"imported but absent from _REGISTRY: {', '.join(missing)}" if missing
        else f"all {len(imported)} adapter modules are in _REGISTRY",
    )


def _route_signature(text: str, path_literal: str) -> str | None:
    """Return the handler signature line for the route whose decorator names it.

    Line-based on purpose. The first version of this check used a single regex
    with `re.S`, and `.*?` is free to span the entire file: it skipped past
    `reveal_mcp_token()` — which takes no parameters at all — and matched the
    `request: Request` of the *next* route, 472 characters later. That reported
    a false "the endpoint is guarded now", which would have pushed a correction
    into a document that was already right.

    Handler signatures in this module are single-line, so scanning forward a few
    lines from the decorator is sufficient and cannot overrun into another route.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if path_literal not in line or not line.lstrip().startswith("@"):
            continue
        for follow in lines[i + 1 : i + 6]:
            stripped = follow.strip()
            if not stripped or stripped.startswith("@") or stripped.startswith("#"):
                continue
            if stripped.startswith(("async def ", "def ")):
                return stripped
            return None  # something else sits between decorator and handler
    return None


def check_defects_still_live(repo: pathlib.Path, rep: Report) -> None:
    """The skill calls three defects 'verified'. Verify they are still there.

    A PASS here means the skill is still accurate — the defect has not been
    fixed upstream. When the maintainer fixes one, this goes red and the skill
    must be updated.
    """
    req = claim_text(repo, "engine/requirements.txt")
    if req is None:
        rep.add("defect 1: mcp bound landed", UNKNOWN, "requirements.txt unreadable")
    else:
        lines = [
            ln.strip() for ln in req.splitlines()
            if ln.strip().startswith("mcp")
        ]
        # This started as the opposite assertion: the defect WAS the absence of an
        # upper bound. Upstream fixed it (c39c79f, 2026-09-24), so the claim is now
        # that the bound is present -- and this check would have gone on demanding
        # an unfixed bug forever. A check that cannot pass is one a reader learns to
        # ignore, so it was inverted when the fix landed rather than left as noise.
        bounded = bool(lines) and any("<" in ln for ln in lines)
        rep.add(
            "defect 1: mcp bound landed",
            PASS if bounded else FAIL,
            (f"{lines[0]!r}" if lines else "no mcp requirement found")
            + ("" if bounded else " — the bound is GONE; the defect is back"),
        )

    conftest = claim_text(repo, "engine/tests/conftest.py")
    if conftest is None:
        rep.add("defect 2: no HOME redirect", UNKNOWN, "conftest.py unreadable")
    else:
        redirected = 'os.environ["HOME"]' in conftest
        rep.add(
            "defect 2: no HOME redirect",
            FAIL if redirected else PASS,
            "conftest redirects HOME — fix landed, update the skill"
            if redirected
            else "conftest still writes to the real ~/.laya",
        )

    mcp_api = claim_text(repo, "engine/laya/api/mcp_api.py")
    if mcp_api is None:
        rep.add("defect 3: token reveal unauth", UNKNOWN, "mcp_api.py unreadable")
    else:
        # The claim is that /mcp/token/reveal hands over the token without a
        # credential. Find that route's handler and read its own parameter list.
        signature = _route_signature(mcp_api, '"/mcp/token/reveal"')
        if signature is None:
            rep.add(
                "defect 3: token reveal unauth",
                FAIL,
                "no handler signature found for /mcp/token/reveal",
            )
        else:
            guarded = any(
                kw in signature
                for kw in ("Depends", "Request", "authorization", "Authorization")
            )
            rep.add(
                "defect 3: token reveal unauth",
                FAIL if guarded else PASS,
                f"{signature} — now takes a credential, update the skill"
                if guarded
                else "handler takes no credential",
            )


def _git(clone: pathlib.Path, *args: str) -> tuple[int, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(clone), *args],
            capture_output=True, text=True, timeout=60,
        )
        return out.returncode, (out.stdout or out.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def check_branches(work: pathlib.Path, rep: Report, offline: bool) -> None:
    """Each prepared branch must exist in its clone, and must not be pushed."""
    for clone_name, branches in PREPARED_BRANCHES.items():
        clone = work / clone_name
        if not clone.is_dir():
            for b in branches:
                rep.add(f"branch {b}", UNKNOWN, f"{clone_name} not present")
            continue

        for b in branches:
            code, _ = _git(clone, "rev-parse", "--verify", "--quiet", b)
            rep.add(
                f"branch {b}",
                PASS if code == 0 else FAIL,
                "" if code == 0 else f"missing from {clone_name}",
            )

        if offline:
            rep.add(f"unpushed in {clone_name}", UNKNOWN, "--offline")
            continue

        # `origin` here is upstream (aayushch/laya). A branch appearing there
        # means it was pushed, which contradicts "deliberately not pushed".
        code, out = _git(clone, "ls-remote", "--heads", "origin")
        if code != 0:
            rep.add(
                f"unpushed in {clone_name}",
                UNKNOWN,
                "cannot reach origin (no network?)",
            )
            continue
        remote = out
        for b in branches:
            pushed = re.search(rf"refs/heads/{re.escape(b)}$", remote, re.M) is not None
            rep.add(
                f"unpushed {b}",
                FAIL if pushed else PASS,
                "PRESENT ON REMOTE — it has been pushed" if pushed else "",
                )


def check_issues(rep: Report, offline: bool, repo_slug: str) -> None:
    """Issue states the skill depends on (#15 closed as #16's duplicate)."""
    if offline:
        for n in EXPECTED_ISSUES:
            rep.add(f"issue #{n}", UNKNOWN, "--offline")
        return

    for number, expected in EXPECTED_ISSUES.items():
        try:
            out = subprocess.run(
                ["gh", "issue", "view", str(number), "--repo", repo_slug,
                 "--json", "state", "--jq", ".state"],
                capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            rep.add(f"issue #{number}", UNKNOWN, f"gh unavailable: {exc}")
            continue
        state = (out.stdout or "").strip()
        if out.returncode != 0 or not state:
            rep.add(f"issue #{number}", UNKNOWN, "gh could not read the issue")
        else:
            rep.add(
                f"issue #{number}",
                PASS if state == expected else FAIL,
                f"{state} (skill relies on {expected})",
            )


def check_issue_drift(repo: pathlib.Path, rep: Report, offline: bool,
                      issues: dict[int, list[str]]) -> None:
    """Did upstream land a commit for an issue we still have a branch for?

    This is the guard that was missing twice. `fix/pin-mcp-below-2` was prepared
    for #16 and the maintainer fixed the same defect the same day (c39c79f, whose
    subject names #16) — the branch had to be retired, and a first-time
    contributor offering merged work is the worst outcome this whole set risks.
    Then round 52 nearly repeated it: work started on #16's diagnostics, which had
    already landed in `sidecar.rs`, and only a look at the base stopped it.

    The range is "since our branch diverged" (`git merge-base <branch> <remote>` to
    the remote tip): commits before that point are already in the base the branch
    was cut from, so they cannot be news to it.

    A mentioning commit does NOT prove the issue is fixed — c39c79f names #16 while
    the issue stayed open pending a release — so this reports UNKNOWN with the
    commits named, never FAIL. The judgement is a human read; the job here is to
    make sure nobody has to remember to make it.
    """
    if not issues:
        rep.add("upstream issue drift", UNKNOWN, "no issue numbers in the submission plan")
        return
    if offline:
        for number in sorted(issues):
            rep.add(f"issue #{number} upstream drift", UNKNOWN, "--offline")
        return

    for number in sorted(issues):
        branches = issues[number]
        base = _merge_base(repo, branches[0])
        if base is None:
            rep.add(f"issue #{number} upstream drift", UNKNOWN,
                    f"could not find the merge base with origin/main for {branches[0]}")
            continue
        code, out = _git(repo, "log", "--oneline", f"{base}..origin/main")
        if code != 0:
            rep.add(f"issue #{number} upstream drift", UNKNOWN, out[:120])
            continue

        pattern = issue_ref_pattern(number)
        mentions = [line.strip() for line in out.splitlines() if pattern.search(line)]
        mentions = list(dict.fromkeys(mentions))
        if mentions:
            rep.add(
                f"issue #{number} upstream drift",
                UNKNOWN,
                f"{len(mentions)} upstream commit(s) since {base[:7]} mention "
                f"#{number} — read them before shipping this branch: "
                + " | ".join(mentions[:3]),
            )
        else:
            rep.add(
                f"issue #{number} upstream drift",
                PASS,
                f"no commit in {base[:7]}..origin/main mentions #{number} "
                f"({len(branches)} branch(es))",
            )


def _merge_base(repo: pathlib.Path, branch: str) -> str | None:
    code, out = _git(repo, "merge-base", branch, "origin/main")
    return out.strip() if code == 0 and out.strip() else None


# ── self-test ───────────────────────────────────────────────────────────────


def _self_test_issue_ref() -> int:
    """Prove the issue matcher is precise, using the false positive it actually had.

    The first version of the drift check used a substring search; run against the
    real upstream log it matched #7 inside a commit about the daily summary, whose
    message quotes `"Review PR #795"`. These cases pin that one and the neighbours
    it could be confused with.
    """
    must_not_match = [
        'Fix: bound the daily summary (observed: "Review PR #795" twice)',  # the real one
        "closes #17",           # a different issue
        "closes #70",           # shares the leading digit
        "P7-6 route ordering",  # the repo's own phase labels, no `#`
        "x#7",                  # not a reference at all
    ]
    must_match = [
        "closes #7",
        "fix(setup): something (#7)",
        "#7: first-run setup progress",
        "see #7, #10",
    ]
    failures = 0
    pattern = issue_ref_pattern(7)
    for text in must_not_match:
        if pattern.search(text):
            print(f"  FAILED: matched #7 in {text!r}")
            failures += 1
    for text in must_match:
        if not pattern.search(text):
            print(f"  FAILED: #7 not matched in {text!r}")
            failures += 1
    if not failures:
        print(f"  ok: #7 matches as a reference and not as a substring "
              f"({len(must_match)} positive, {len(must_not_match)} negative cases)")
    return failures


def self_test(repo: pathlib.Path) -> int:
    """Prove the checks can fail. A guard that cannot go red is not a guard.

    Runs the same functions against an empty directory, where every existent
    claim is false, and asserts they report FAIL rather than passing or
    quietly reporting UNKNOWN.
    """
    print("self-test: running the checks against an empty tree")
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        empty = pathlib.Path(tmp)
        rep = Report()
        check_paths(empty, rep)
        check_counts(empty, rep)
        check_defects_still_live(empty, rep)

        path_rows = [r for r in rep.rows if r[0].startswith("path ")]
        bad_paths = [r for r in path_rows if r[1] != FAIL]
        if bad_paths:
            print(f"  FAILED: {len(bad_paths)} path claims did not go red on an empty tree")
            for name, status, _ in bad_paths[:5]:
                print(f"    {name}: {status}")
            failures += 1
        else:
            print(f"  ok: all {len(path_rows)} path claims go red when the file is absent")

        # An empty tree must not be mistaken for "everything is fine".
        if rep.failed == 0:
            print("  FAILED: empty tree produced no failures at all")
            failures += 1
        else:
            print(f"  ok: empty tree produced {rep.failed} failures")

        # Unreadable inputs must be UNKNOWN, never PASS.
        unknown_rows = [r for r in rep.rows if r[1] == UNKNOWN]
        if not unknown_rows:
            print("  FAILED: unreadable inputs were not reported as UNKNOWN")
            failures += 1
        else:
            print(f"  ok: {len(unknown_rows)} unreadable inputs reported UNKNOWN, not PASS")

    # The real tree must not be reported as a total failure by the same code.
    rep = Report()
    check_paths(repo, rep)
    if rep.failed:
        print(f"  FAILED: {rep.failed} path claims fail on the real repo — fix the skill")
        failures += 1
    else:
        print(f"  ok: all {len(REQUIRED_PATHS)} path claims pass on the real repo")

    failures += _self_test_issue_ref()
    failures += _self_test_route_guards()
    failures += _self_test_platform_registration()
    failures += _self_test_skill_paths(repo)

    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def _self_test_skill_paths(repo: pathlib.Path) -> int:
    """Prove a path named in the skill but absent from the repo goes red.

    This is the defect the script exists for: SKILL.md named
    `engine/laya/api/main.py`, a path that has never existed in any commit.
    """
    print("self-test: skill path extraction")
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        fake_skill = pathlib.Path(tmp) / "SKILL.md"
        fake_skill.write_text(
            "The entrypoint is `engine/laya/api/main.py` and the config is "
            "`engine/laya/config.py`.\n",
            encoding="utf-8",
        )
        rep = Report()
        check_skill_paths(fake_skill, repo, rep)

        rows = {name: status for name, status, _ in rep.rows}
        bad = rows.get("skill path engine/laya/api/main.py")
        good = rows.get("skill path engine/laya/config.py")

        if bad != FAIL:
            print("  FAILED: a nonexistent named path was not reported as FAIL")
            failures += 1
        else:
            print("  ok: a path the repo does not have goes red")

        if good != PASS:
            print("  FAILED: an existing named path was not reported as PASS")
            failures += 1
        else:
            print("  ok: a path the repo does have passes")

    # A skill that names no paths must be UNKNOWN, not a silent pass.
    with tempfile.TemporaryDirectory() as tmp:
        bare = pathlib.Path(tmp) / "SKILL.md"
        bare.write_text("No paths are named here at all.\n", encoding="utf-8")
        rep = Report()
        check_skill_paths(bare, repo, rep)
        if rep.rows and rep.rows[0][1] == UNKNOWN:
            print("  ok: a skill naming no paths reports UNKNOWN, not PASS")
        else:
            print("  FAILED: a skill naming no paths did not report UNKNOWN")
            failures += 1

    return failures


def _self_test_platform_registration() -> int:
    """Prove an imported-but-unregistered adapter is caught.

    This is the mistake CLAUDE.md's "adding a platform is one file" invites:
    the adapter is written, imported, and never registered, so the platform
    silently never resolves.
    """
    print("self-test: egress adapter registration")
    failures = 0

    good = (
        "from laya.egress.platforms import (\n"
        "    github,\n    jira,\n)\n\n"
        '_REGISTRY: dict[str, Platform] = {\n'
        '    "github": github.PLATFORM,\n'
        '    "jira": jira.PLATFORM,\n'
        "}\n"
    )
    forgotten = (
        "from laya.egress.platforms import (\n"
        "    github,\n    jira,\n    notion,\n)\n\n"
        '_REGISTRY: dict[str, Platform] = {\n'
        '    "github": github.PLATFORM,\n'
        '    "jira": jira.PLATFORM,\n'
        "}\n"
    )

    cases = (
        ("a fully registered set passes", good, set(), {"github", "jira"}),
        ("an imported but unregistered adapter is caught", forgotten,
         {"notion"}, {"github", "jira", "notion"}),
    )
    for description, source, expect_missing, expect_imports in cases:
        imported = _platform_imports(source)
        registered = _platform_registered(source)
        missing = imported - registered
        if imported != expect_imports:
            print(f"  FAILED: parsed imports {sorted(imported)} — {description}")
            failures += 1
        elif missing != expect_missing:
            print(f"  FAILED: missing={sorted(missing)}, expected "
                  f"{sorted(expect_missing)} — {description}")
            failures += 1
        else:
            print(f"  ok: {description}")

    # Unreadable input must be UNKNOWN, never a silent pass.
    rep = Report()
    check_platform_registration(pathlib.Path("/nonexistent"), rep)
    if rep.rows and rep.rows[0][1] == UNKNOWN:
        print("  ok: an unreadable module reports UNKNOWN, not PASS")
    else:
        print("  FAILED: an unreadable module did not report UNKNOWN")
        failures += 1

    return failures


def _self_test_route_guards() -> int:
    """Prove the credential check reads the right handler, in both directions.

    The regression this guards: `reveal_mcp_token()` takes no parameters, but a
    later route in the same file takes `request: Request`. A check that scans
    forward too far reads the wrong function and reports the endpoint as fixed.
    """
    print("self-test: route credential detection")
    failures = 0

    guarded_source = '''\
@router.get("/mcp/token/reveal", response_model=TokenResponse)
async def reveal_mcp_token(request: Request) -> TokenResponse:
    return TokenResponse(token=token)
'''
    unguarded_then_guarded = '''\
@router.get("/mcp/token/reveal", response_model=TokenResponse)
async def reveal_mcp_token() -> TokenResponse:
    """Loopback-trusted."""
    return TokenResponse(token=token)


@router.delete("/mcp/token")
async def delete_token(request: Request) -> dict[str, str]:
    return {}
'''

    cases = (
        ("a guarded reveal handler is detected", guarded_source, True),
        (
            "an unguarded reveal handler followed by a Request-taking route "
            "is NOT reported as guarded",
            unguarded_then_guarded,
            False,
        ),
    )

    for description, source, expect_guarded in cases:
        sig = _route_signature(source, '"/mcp/token/reveal"')
        if sig is None:
            print(f"  FAILED: no signature found — {description}")
            failures += 1
            continue
        guarded = any(
            kw in sig for kw in ("Depends", "Request", "authorization", "Authorization")
        )
        if guarded != expect_guarded:
            print(f"  FAILED: expected guarded={expect_guarded}, got {guarded} — {description}")
            failures += 1
        else:
            print(f"  ok: {description}")

    return failures


# ── entrypoint ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", type=pathlib.Path, default=pathlib.Path.home() / "Work/laya-inspect",
        help="path to the Laya checkout (default: ~/Work/laya-inspect)",
    )
    parser.add_argument(
        "--work-dir", type=pathlib.Path, default=pathlib.Path.home() / "Work",
        help="directory holding the laya-* clones (default: ~/Work)",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="skip the checks that need the network or gh (reported UNKNOWN)",
    )
    parser.add_argument(
        "--repo-slug", default="aayushch/laya", help="owner/repo for the issue checks",
    )
    parser.add_argument(
        "--skill", type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent / "skills/laya/SKILL.md",
        help="the SKILL.md to check named paths against (default: this preset's own)",
    )
    parser.add_argument("--self-test", action="store_true", help="prove the checks can fail")
    args = parser.parse_args(argv)

    repo = args.repo.expanduser().resolve()
    work = args.work_dir.expanduser().resolve()

    if args.self_test:
        return self_test(repo)

    if not (repo / "engine").is_dir():
        print(f"error: {repo} does not look like a Laya checkout", file=sys.stderr)
        return 2

    print(f"verifying the `laya` skill's claims against {repo}")
    print()
    rep = Report()
    check_skill_paths(args.skill, repo, rep)
    check_paths(repo, rep)
    check_counts(repo, rep)
    check_platform_registration(repo, rep)
    check_defects_still_live(repo, rep)
    check_branches(work, rep, args.offline)
    check_issues(rep, args.offline, args.repo_slug)
    check_issue_drift(repo, rep, args.offline, plan_issues(work))
    rep.render()

    print()
    print(
        f"{sum(1 for _, s, _ in rep.rows if s == PASS)} pass, "
        f"{rep.failed} FAIL, {rep.unknown} unknown"
    )
    if rep.failed:
        print("\nthe skill contradicts the repository — update it before relying on it")
        return 1
    if rep.unknown:
        print("\nunknown claims were not treated as verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
