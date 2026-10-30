#!/usr/bin/env python3
"""Audit the prepared Laya contributions against PREPARED-WORK-INDEX.md.

Read-only. Verifies, from the index's own claims:

  1. every documented branch exists at the documented commit
  2. the documented branches can each be their own PR: file-disjoint pairs pass, and a
     pair that shares a file must be DECLARED and must merge together cleanly (the
     proxy for independence is independence, not disjointness)
  3. upstream main has not moved (so the recorded merge checks still hold) and
     nothing of ours has been upstreamed
  4. each clone's safety state, i.e. whether running pytest there would delete the
     developer's MCP bearer token
  5. each clone's remotes, i.e. whether the fork is wired (the submission footgun:
     a bare `gh repo fork --clone=false` adds no remote, so `git push origin`
     targets the maintainer's repo)

Run:
    python3 "$DSH_HOME/.agent-presets/laya-contributor/tools/audit_prepared_work.py"

Exits 0 when every check passes, 1 otherwise. Nothing is pushed, fetched, or
written: `git ls-remote` is the only network call, and it is read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_INDEX = Path("/home/logic/Work/PREPARED-WORK-INDEX.md")
DEFAULT_REPO = "/home/logic/Work/laya-inspect"
# Where the nine pushable repositories live. Derived from the index's own path rather
# than typed twice, so moving the workspace cannot leave the runbook check pointing at
# an empty directory and quietly counting zero pushes.
DEFAULT_WORK_DIR = DEFAULT_INDEX.parent
HERE = pathlib.Path(__file__).resolve().parent
CLASSIFIER = Path("/home/logic/.dsh/.agent-presets/laya-contributor/tools/check_laya_home.py")
UPSTREAM = "aayushch/laya"

# Where a copy of the index is kept, and how many. See snapshot_index().
INDEX_HISTORY = pathlib.Path(os.environ.get("DSH_HOME", pathlib.Path.home() / ".dsh")) / "index-history"
INDEX_HISTORY_KEEP = 20


def snapshot_index(index: Path, count: int,
                   history: pathlib.Path | None = None) -> str:
    """Keep a copy of the index before anything can rewrite it; report a count drop.

    Two real failures this answers. A scripted edit that matched the wrong anchor
    deleted ~410 lines of this file — no git, no backup — and it had to be rebuilt
    by hand from the branches. The audit *did* catch that (`0 claims parsed`), so
    detection was never the gap; recovery was. And nothing distinguished "the
    index legitimately shrank" from "the index lost most of its content", which is
    why the branch count travels with the copy: a drop is called out in the same
    run that reports it.

    `history` is injectable so the self-test can exercise this without writing into
    the real history — the first version did write there, from a synthetic
    one-claim index, which is exactly the kind of test pollution that then makes a
    later run report a bogus drop.

    Returns a note to print, or "" when there is nothing to say.
    """
    store = history if history is not None else INDEX_HISTORY
    try:
        source = index.read_text(encoding="utf-8")
    except OSError as exc:
        return f"could not read the index to snapshot it: {exc}"
    try:
        store.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        (store / f"{stamp}-{count}.md").write_text(source, encoding="utf-8")
        kept = sorted(store.glob("*.md"))
        for old in kept[:-INDEX_HISTORY_KEEP]:
            old.unlink(missing_ok=True)
    except OSError as exc:
        return f"could not snapshot the index: {exc}"

    previous = None
    for other in reversed(kept[:-1] if kept else []):
        try:
            previous = int(other.stem.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            continue
        break
    if previous is not None and count < previous:
        return (f"the index documents {count} branch(es), down from {previous} in the "
                f"previous run — that is the shape of an edit accident; every run's copy "
                f"is in {store}")
    return ""

BRANCH_LINE = re.compile(r"\|\s*Branch\s*\|\s*`([^`]+)`\s*(?:\(([^)]*)\))?(.*?)\|")
LOCATION_LINE = re.compile(r"\|\s*Location\s*\|\s*`([^`]+)`")
COMMIT_SHA = re.compile(r"\b([0-9a-f]{7,40})\b")
REPO_INLINE = re.compile(r"in\s+`([^`]+)`")


# Pairs that legitimately touch the same file. Keyed rather than exempted by filename: a
# blanket "this file may overlap" rule would stop the check being able to fail, and the whole
# point of declaring a pair is that the reason is arguable in a sentence.
ALLOWED_OVERLAP = {
    # Cross-clone pairs: `merge-tree` cannot span two working trees, so these are declared
    # with the evidence from a real merge rather than re-verified on every run. Both were
    # re-verified on 2026-09-25, after every branch involved had changed.
    frozenset(("feat/persist-tool-call-references", "feat/full-page-coding-chat")):
        "both touch the chat surface across two clones (chat_api.py, ws_router.py, "
        "models/chat.py, pipeline/chat.py). Fetched the chat branch into laya-inspect and "
        "merged it into the tool-references branch: no conflicts in any of the four, and 58 "
        "chat tests pass on the combination (test_chat_tool_calls, test_chat_focus, "
        "test_chat_api)",
    frozenset(("feat/full-page-coding-chat", "feat/cursor-cli-adapter")):
        "documentation only: the chat branch updates README/CLAUDE for the full-page route, "
        "the cursor branch for the fifth agent. Fetched the chat branch into laya-inspect and "
        "merged it into the cursor branch: no conflicts in CLAUDE.md or README.md",
    # Same-clone pairs: re-verified by `merge-tree` on every run, which must come back clean.
    frozenset(("fix/omni-attention-wipe-guard", "feat/omni-open-items-input")):
        "both halves of #10 in one file: the guard rejects a synthesis that empties attention "
        "while subjects are open, the candidates block gives an already-starved space a way "
        "back. Merged in a scratch tree with no conflicts, and 49 tests pass on the "
        "combination (test_omni_resynthesis.py + test_omni_open_items.py)",
    frozenset(("feat/persist-tool-call-references", "fix/tests-isolate-laya-home")):
        "both add to engine/tests/conftest.py: the isolation branch rewrites the header that "
        "has to run before the first `laya` import, this one appends a conversation helper. "
        "merge-tree is clean",
    frozenset(("fix/omni-unitemised-cards", "fix/omni-attention-wipe-guard")):
        "both halves of the same function: the guard judges what the model returned, this one "
        "keeps what it left out. They share pipeline/omni.py and its test file. All three omni "
        "branches were merged into one scratch tree in this order — no conflicts in either file "
        "— and 55 tests pass on the combination (test_omni_resynthesis.py + "
        "test_omni_open_items.py)",
    frozenset(("fix/omni-unitemised-cards", "feat/omni-open-items-input")):
        "pipeline/omni.py again: the open-items branch adds an input to the prompt, this one "
        "adds an item to the stored result. merge-tree is clean, and the same three-way merge "
        "above covers the combination",
}


def plan_size(here: Path | None = None) -> int:
    """How many branches the submission plan actually contains, or 0 if it cannot be read."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_spw_for_audit", (here or pathlib.Path(__file__).resolve().parent)
        / "submit_prepared_work.py")
    if spec is None or spec.loader is None:
        return 0
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:                                            # noqa: BLE001
        return 0
    return len(getattr(module, "PLAN", ()))


# Present-tense statements of how large the prepared set is. Both were stale at once
# (the banner said "Ten branches are prepared" while the plan held twelve, and the
# composed-set paragraph said "all eleven are merged"), because the set grew twice and
# nothing tied the prose to it. A count in a document is a claim like any other.
# The tail of this heading changed twice ("one more was retired" -> "two were retired") and
# the first pattern pinned it, so the check silently stopped reading the number and said so
# only as a note. Anchor on the part that carries the count.
BANNER_COUNT = re.compile(r"^> ## ⚠️ ([A-Za-z]+) branches are prepared", re.M)
COMPOSE_COUNT = re.compile(r"\ball (\d+) are merged into a scratch")
NUMBER_WORDS = {word: i for i, word in enumerate(
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
    "Fourteen Fifteen".split())}


def stated_branch_counts(text: str, size: int) -> tuple[list[str], list[str]]:
    """(failures, notes) for the index's statements of the current set size.

    A mismatch is a failure — the index is the document the user follows, and it was
    telling them ten branches existed when twelve did. A *missing* phrase is a note
    rather than a failure: the audit cannot check a sentence it cannot read, and saying
    so out loud is the honest outcome, not passing quietly.
    """
    failures: list[str] = []
    notes: list[str] = []
    banner = BANNER_COUNT.search(text)
    if banner:
        word = banner.group(1)
        number = NUMBER_WORDS.get(word)
        if number is None:
            notes.append(f"the banner says `{word} branches`; this audit reads cardinals "
                         f"up to fifteen, so that count is unchecked")
        elif number != size:
            failures.append(f"the banner says {number} branches are prepared; the "
                            f"submission plan has {size}")
    else:
        notes.append("the banner no longer states the branch count in the form this audit "
                     "reads (`> ## ⚠️ <Word> branches are prepared`), so it is unchecked")
    compose = COMPOSE_COUNT.search(text)
    if compose:
        number = int(compose.group(1))
        if number != size:
            failures.append(f"the composed-set paragraph says all {number} are merged into "
                            f"a scratch tree; the submission plan has {size}")
    else:
        notes.append("the composed-set paragraph no longer states `all N are merged into a "
                     "scratch`, so that count is unchecked")
    return failures, notes


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as error:
        return 127, str(error)


def plan_branch_names(here: Path | None = None) -> list[str]:
    """The exact branch names the submission plan would ship, or [] if unreadable."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_spw_names_for_audit", (here or pathlib.Path(__file__).resolve().parent)
        / "submit_prepared_work.py")
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:                                            # noqa: BLE001
        return []
    return [branch for branch, _clone, _body, _desc in getattr(module, "PLAN", ())]


# ── the index's own numbers ─────────────────────────────────────────────────
# PREPARED-WORK-INDEX.md is the document the user reads, and it quotes counts in two
# places nothing verified: a per-branch "engine **N**" line inside each branch section,
# and the composed-set table ("engine **1211 passed**", "combined **49 files changed,
# +5432 / −189**"). The composed figures existed nowhere a machine could read them until
# `compose_prepared_branches.py` began writing `composed-counts.json` — which is why the
# check below can be a comparison rather than a hope.
ENGINE_CLAIM = re.compile(r"engine \*\*(\d+)(?: passed)?\*\*")
BRANCH_ROW = re.compile(r"^\| Branch \| `([^`]+)`")
COMPOSED_HEAD = "## The composed set"
COMPOSED_STOP = "**Earlier compositions (superseded, kept as a record).**"
# The row names the clone it is talking about — there are two records, and taking the
# last one compared the table against `laya-chat`'s 18-file diff instead of
# `laya-inspect`'s 49.
COMBINED_CLAIM = re.compile(r"`([a-z][a-z0-9-]*)` combined \*\*(\d+) files? changed, \+(\d+) / −(\d+)\*\*")
PASSED_ANY = re.compile(r"\*\*(\d+) passed")


def index_branch_claims(text: str) -> list[tuple[str, int]]:
    """(branch, engine count) for every "engine **N**" inside a branch section."""
    claims: list[tuple[str, int]] = []
    current = ""
    for line in text.splitlines():
        row = BRANCH_ROW.match(line)
        if row:
            current = row.group(1)
            continue
        if line.startswith("## "):
            current = ""          # leaving the branch sections entirely
            continue
        if current:
            claims.extend((current, int(n)) for n in ENGINE_CLAIM.findall(line))
    return claims


def index_figure_claims(text: str, manifest: dict,
                        composed: dict | None) -> tuple[list[str], list[str]]:
    """(failures, notes) for the counts the index states about the prepared work."""
    failures: list[str] = []
    notes: list[str] = []

    measured: dict[str, int] = {}
    for entry in (manifest.get("entries") or {}).values():
        if entry.get("variant") or not entry.get("green"):
            continue
        passed = (entry.get("figures") or {}).get("passed")
        if isinstance(passed, int) and entry.get("suite") == "engine":
            measured[entry["branch"]] = passed

    for branch, claimed in index_branch_claims(text):
        actual = measured.get(branch)
        if actual is None:
            notes.append(f"the index states engine **{claimed}** for `{branch}`, which has "
                         f"no measurement in the manifest — unchecked")
        elif claimed != actual:
            failures.append(f"the index says engine **{claimed}** for `{branch}`; the "
                            f"measured count is {actual}")

    # The composed table. Scoped to the section and cut before the superseded paragraph,
    # whose counts are deliberately historical.
    if COMPOSED_HEAD in text:
        section = text.split(COMPOSED_HEAD, 1)[1]
        section = section.split(COMPOSED_STOP, 1)[0]
        if composed is None:
            notes.append("the composed table's figures are unchecked — no "
                         "composed-counts.json; run compose_prepared_branches.py")
        else:
            recorded = " ".join(
                [c.get("detail", "") for r in composed.get("records", [])
                 for c in r.get("checks", [])]
                + [r.get("combined", "") for r in composed.get("records", [])])
            for figure in sorted({int(n) for n in PASSED_ANY.findall(section)}):
                if str(figure) not in recorded:
                    failures.append(f"the composed table says **{figure} passed**, which is "
                                    f"not in the recorded composed run "
                                    f"({composed.get('generated', 'undated')})")
            claim = COMBINED_CLAIM.search(section)
            if claim:
                which = claim.group(1)
                want = tuple(int(x) for x in claim.groups()[1:])
                # The record keeps git's own phrasing ("49 files changed, 5432
                # insertions(+), 189 deletions(-)") while the table is written "+5432 /
                # −189". The first version of this compared the index against the table's
                # format, found nothing, and skipped the comparison in silence — a check
                # that cannot fail is the thing this whole exercise is about.
                RECORDED_STAT = re.compile(
                    r"(\d+) files? changed, (\d+) insertions?\(\+\), (\d+) deletions?\(-\)")
                got = None
                for record in composed.get("records", []):
                    if record.get("clone") != which:
                        continue
                    match = RECORDED_STAT.search(record.get("combined", ""))
                    if match:
                        got = tuple(int(x) for x in match.groups())
                if got is None:
                    notes.append("the composed record has no parseable diffstat, so the "
                                 "table's file/insertion/deletion claim is unchecked")
                elif got != want:
                    failures.append(f"the composed table says {want[0]} files +{want[1]}/−{want[2]}"
                                    f"; the recorded composition is {got[0]} files "
                                    f"+{got[1]}/−{got[2]}")
            # "12/12, no conflicts" — the merge count and the absence of conflicts.
            merge_claim = re.search(r"\*\*(\d+)/(\d+), no conflicts\*\*", section)
            merged = sum(len(r.get("branches", [])) for r in composed.get("records", []))
            conflicted = [r["clone"] for r in composed.get("records", []) if r.get("conflict")]
            if merge_claim:
                if int(merge_claim.group(2)) != merged:
                    failures.append(f"the composed table says {merge_claim.group(2)} branches "
                                    f"merged; the recorded run merged {merged}")
                if conflicted:
                    failures.append(f"the composed table says 'no conflicts'; the recorded "
                                    f"run conflicted in {', '.join(conflicted)}")
    else:
        notes.append("the index no longer has a composed-set section, so those figures are "
                     "unchecked")
    return failures, notes


# ── diff hygiene ────────────────────────────────────────────────────────────
# What a reviewer notices before reading a line of the change: a binary blob, a file whose
# executable bit moved, a conflict marker, trailing whitespace. `git diff` answers all of
# it, so this wraps git rather than re-deriving it — with one trap worth remembering. The
# raw format is `:100644 100644 <sha> <sha> M\tpath`, and an ADDED file reads
# `:000000 100644 …`, so comparing the mode strings without reading the status reported
# eleven "mode changes" that were all just new files. Third time in three rounds that a
# detector of mine fired on its own misreading; the status column is the answer.
RAW_DIFF = re.compile(r"^:(\d{6}) (\d{6}) [0-9a-f]+ [0-9a-f]+ ([A-Z])\t(.+)$")
# Whitespace git flags. Kept as NOTES rather than failures, with the reason: this
# repository has two workflows (pages.yml, release.yml), no linter and no pre-commit hook,
# so a blank line at EOF fails nothing upstream. Two branches have one. Failing the audit
# for it would pressure a rebase that changes every recorded SHA to fix a line no job
# reads; saying so is the honest middle.
WHITESPACE_NITS = ("new blank line at EOF", "trailing whitespace", "space before tab",
                   "indent with spaces")


def parse_mode_changes(raw_text: str) -> list[tuple[str, str, str]]:
    """(old, new, path) for real mode changes — an addition is not one."""
    changes = []
    for line in raw_text.splitlines():
        match = RAW_DIFF.match(line)
        if not match:
            continue
        old, new, status, path = match.groups()
        if status in ("A", "D") or old == new:
            continue
        changes.append((old, new, path))
    return changes


def parse_binary_files(numstat_text: str) -> list[str]:
    """Paths whose numstat is `-\t-` — git will not diff them as text."""
    return [line.split("\t")[-1] for line in numstat_text.splitlines()
            if line.startswith("-\t-")]


def classify_diff_check(output: str) -> tuple[list[str], list[str]]:
    """(failures, notes) for `git diff --check` output."""
    failures: list[str] = []
    notes: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "conflict" in line.lower():
            failures.append(f"a conflict marker is committed: {line[:100]}")
        elif any(nit in line for nit in WHITESPACE_NITS):
            notes.append(f"whitespace: {line[:100]}")
        else:
            notes.append(f"git diff --check: {line[:100]}")
    return failures, notes


def diff_hygiene(repo: str, branch: str) -> tuple[list[str], list[str]]:
    """(failures, notes) for the diff a reviewer would open."""
    failures: list[str] = []
    notes: list[str] = []
    raw = run(["git", "-C", repo, "diff", "--raw", f"main...{branch}"])[1]
    for old, new, path in parse_mode_changes(raw):
        failures.append(f"{branch}: {path} changes mode {old} -> {new}")
    numstat = run(["git", "-C", repo, "diff", "--numstat", f"main...{branch}"])[1]
    for path in parse_binary_files(numstat):
        failures.append(f"{branch}: {path} is binary — git cannot show the change as text")
    code, out = run(["git", "-C", repo, "diff", "--check", f"main...{branch}"])
    check_fails, check_notes = classify_diff_check(out if code != 0 else "")
    failures.extend(check_fails)
    notes.extend(check_notes)
    return failures, notes


# ── the runbook the user actually follows ───────────────────────────────────
# "DO THIS, IN ORDER" is not documentation, it is the script someone runs, and nothing
# checked it. Two real drifts by 2026-09-25: the shell block still said `# 19 commits`
# for reputation (23) and `# 11` for the four figure-synced repos (15 each), under a
# heading that said 69 where the true total was 89. The counts move every time a sync
# commits, so a comment copied once is stale by the next round — and it is the number a
# reader uses to decide what they are about to publish.
#
# The other half is worse than stale: if a branch fell out of the `--only` batches, the
# user would ship eleven PRs, be told everything succeeded, and never learn the twelfth
# was never opened. That is now checked by counting coverage, not by reading.
PUSH_LINE = re.compile(r"git -C (/home/logic/Work/(\S+))\s+push origin (\S+)\s+#\s*(\d+)")
PUSH_TOTAL = re.compile(r"[Pp]ush the nine repositories carrying this work — (\d+) commits")
ONLY_FLAG = re.compile(r"--only\s+([A-Za-z0-9._/-]+)")
# Anchored on the tool directory, NOT on a bare basename. The first pass of this matched
# `([a-z_]+\.py)` anywhere and invented six "missing tools" out of prose that named
# repository files (`engine/tests/conftest.py`, `pipeline/omni.py`) — a detector firing on
# its own text, which is the same mistake the test-integrity detector made and the same
# one worth never repeating.
TOOL_PATH = re.compile(r"agent-presets/laya-contributor/tools/([a-z_]+\.py)")


def count_unpushed(repo: pathlib.Path, branch: str) -> int | None:
    code, out = run(["git", "-C", str(repo), "rev-list", "--count", f"origin/{branch}..{branch}"])
    try:
        return int(out.splitlines()[-1]) if code == 0 else None
    except (ValueError, IndexError):
        return None


def runbook_facts(text: str, plan_branches: list[str], work_dir: pathlib.Path,
                  tools_dir: pathlib.Path, counter=None) -> tuple[list[str], list[str]]:
    """(failures, notes) for the `DO THIS, IN ORDER` block.

    `counter` is injectable so the self-test can exercise the stale-count half without a
    repository whose unpushed count it controls. A check whose only proof needs the real
    workspace is a check that stops being tested the moment the workspace changes.
    """
    counter = counter or count_unpushed
    failures: list[str] = []
    notes: list[str] = []

    named = ONLY_FLAG.findall(text)
    for branch in plan_branches:
        seen = named.count(branch)
        if seen == 0:
            failures.append(f"the runbook never names `{branch}` in an `--only`, so that "
                            f"branch would never be submitted")
        elif seen > 1:
            failures.append(f"the runbook names `{branch}` in {seen} `--only` flags")
    for branch in sorted(set(named) - set(plan_branches)):
        failures.append(f"the runbook submits `{branch}`, which is not in the plan")

    total = 0
    rows = PUSH_LINE.findall(text)
    if not rows:
        notes.append("the runbook has no `git -C … push origin … # N` lines, so the push "
                     "counts are unchecked")
    for path, repo_name, branch, stated in rows:
        actual = counter(pathlib.Path(path), branch)
        if actual is None:
            notes.append(f"{repo_name}: could not count unpushed commits, so the stated "
                         f"{stated} is unchecked")
            continue
        total += actual
        if actual != int(stated):
            failures.append(f"the runbook says {stated} commits for {repo_name}; "
                            f"origin/{branch}..{branch} is {actual}")
    match = PUSH_TOTAL.search(text)
    if match and rows:
        if int(match.group(1)) != total:
            failures.append(f"the runbook heading says {match.group(1)} commits; the nine "
                            f"repositories carry {total}")
    elif not match:
        notes.append("the runbook heading no longer states the commit total, so it is unchecked")

    for tool in sorted(set(TOOL_PATH.findall(text))):
        if not (tools_dir / tool).is_file():
            failures.append(f"the runbook invokes `{tool}`, which is not in {tools_dir}")
    return failures, notes


# ── test integrity ──────────────────────────────────────────────────────────
# Two PR bodies state outright that no existing test was weakened, skipped or deleted.
# That is the one claim a maintainer cannot check by reading a 500-line diff, and it is
# mechanically checkable — but only with detectors that do not fire on their own prose.
# The first prototype of this reported a *rename* as a deletion (parsing
# `it('offers "none" ...` up to the quote inside the string) and `process.exit(` as a
# skipped test (`xit(`): two false positives, of exactly the kind this workspace keeps
# publishing about. So the rule is: COUNT definitions rather than match names (a rename
# is -1/+1 and nets out), compare against the MERGE BASE rather than `main` (a test
# upstream added must not read as one this branch removed), and anchor every skip
# pattern on a word boundary.
TEST_PY_DEF = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.M)
TEST_JS_DEF = re.compile(r"(?:^|\n)\s*(?:it|test)\(\s*[`'\"]", re.M)
TEST_ASSERT = re.compile(r"(^\s*assert\s|expect\(|assert_that\(|self\.assert)", re.M)
TEST_SKIP = re.compile(r"(?:pytest\.mark\.(?:skip|xfail)|pytest\.skip\(|"
                       r"(?<![A-Za-z_.])xit\(|(?<![A-Za-z_])xdescribe\(|"
                       r"(?:it|test|describe)\.skip\()")


def is_test_file(path: str) -> bool:
    if "/tests/" in path or "/test_" in path or path.startswith("tests/"):
        return True
    base = path.rsplit("/", 1)[-1]
    return bool(re.match(r"test_.*\.py$", base)) or bool(re.search(r"\.(test|spec)\.", base))


def test_definitions(text: str, path: str) -> int:
    """How many tests a file defines. Counting, not naming: see the note above."""
    if path.endswith(".py"):
        return len(TEST_PY_DEF.findall(text))
    if path.endswith((".ts", ".js", ".mjs", ".svelte")):
        return len(TEST_JS_DEF.findall(text))
    return 0


def test_integrity(repo: str, branch: str) -> tuple[list[str], list[str], int]:
    """(failures, notes, test files checked) for one branch.

    A failure means the branch's green came at a test's expense: a file that defined
    fewer tests than at the branch's own merge base, or a newly added skip/xfail marker.
    A drop in the *assertion* count is a note rather than a failure — rewriting a test
    to assert something narrower is legitimate — but it is the signal "weakened" would
    leave behind, so it is printed rather than left for a reader to notice.

    THE BOUNDARY, stated because a check that cannot see something should say so: the
    baseline is the merge base, so a test file the branch *created* has no baseline and
    its tests cannot be "removed". Verified deliberately — deleting one `it()` from the
    chat branch's own new `composer.test.ts` is not reported, while deleting one from
    `datetime.test.ts`, which exists on `main`, is reported as
    `1 test(s) removed (12 -> 11)`. That is the right reading of "no existing test
    deleted": a test this branch introduced is not pre-existing. What it does not cover
    is a branch that adds a test and then removes it within its own series.
    """
    code, base = run(["git", "-C", repo, "merge-base", "main", branch])
    if code != 0 or not base:
        return [], [f"{branch}: no merge base with main, so test integrity was not checked"], 0
    changed = run(["git", "-C", repo, "diff", "--name-only", f"main...{branch}"])[1].split()
    files = [path for path in changed if is_test_file(path)]
    failures: list[str] = []
    notes: list[str] = []
    for path in files:
        after_code, after = run(["git", "-C", repo, "show", f"{branch}:{path}"])
        if after_code != 0:
            continue
        before_code, before = run(["git", "-C", repo, "show", f"{base}:{path}"])
        before_count = test_definitions(before, path) if before_code == 0 else 0
        after_count = test_definitions(after, path)
        if after_count < before_count:
            failures.append(f"{branch}: {before_count - after_count} test(s) removed from "
                            f"{path} ({before_count} -> {after_count})")
        before_asserts = len(TEST_ASSERT.findall(before)) if before_code == 0 else 0
        after_asserts = len(TEST_ASSERT.findall(after))
        if after_asserts < before_asserts:
            notes.append(f"{branch}: {path} carries {before_asserts - after_asserts} fewer "
                         f"assertion(s) than at the base ({before_asserts} -> {after_asserts})")
        diff = run(["git", "-C", repo, "diff", f"main...{branch}", "--", path])[1]
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++") and TEST_SKIP.search(line[1:]):
                failures.append(f"{branch}: adds a skip marker in {path} — "
                                f"`{line[1:].strip()[:70]}`")
    return failures, notes, len(files)


class Audit:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []
        self.notes: list[str] = []

    def check(self, label: str, ok: bool, note: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  ok    {label}" + (f"  ({note})" if note else ""))
        else:
            self.failed.append(label + (f"  ({note})" if note else ""))
            print(f"  FAIL  {label}" + (f"  ({note})" if note else ""))

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  note  {text}")


def parse_claims(index: Path) -> list[dict]:
    claims: list[dict] = []
    current_repo = DEFAULT_REPO
    section = ""
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line.strip("# ").strip()
        location = LOCATION_LINE.search(line)
        if location:
            current_repo = location.group(1)
            continue
        match = BRANCH_LINE.search(line)
        if not match:
            continue
        branch = match.group(1).strip()
        parents = match.group(2) or ""
        tail = match.group(3) or ""
        shas = COMMIT_SHA.findall(parents)
        if not shas:
            continue
        inline = REPO_INLINE.search(tail)
        repo = inline.group(1) if inline else current_repo
        claims.append(
            {
                "section": section,
                "branch": branch,
                "head": shas[-1],
                "all_shas": shas,
                "repo": repo,
            }
        )
    return claims


def self_test() -> int:
    """Prove this audit can fail, on a synthetic index that lies.

    The load-bearing claim here is "every documented branch exists at the
    documented commit". If that check cannot go red, the audit is decoration —
    so it is exercised against an index naming a branch that does not exist.
    """
    import contextlib
    import io
    import tempfile

    failures = 0
    print("self-test: the audit can detect a bad claim")

    with tempfile.TemporaryDirectory() as tmp:
        idx = Path(tmp) / "INDEX.md"
        idx.write_text(
            "# Index\n\n"
            "## 1. A section that lies\n\n"
            "| | |\n|---|---|\n"
            "| Location | `laya-inspect` |\n"
            "| Branch | `fix/no-such-branch-xyz` (commit `deadbee`) |\n",
            encoding="utf-8",
        )

        claims = parse_claims(idx)
        if len(claims) != 1 or claims[0]["branch"] != "fix/no-such-branch-xyz":
            print(f"  FAILED: could not parse the synthetic claim: {claims}")
            failures += 1
        else:
            print("  ok: a branch and commit are parsed out of the index")

        argv = sys.argv
        sys.argv = [argv[0], "--index", str(idx), "--offline"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = main()
        finally:
            sys.argv = argv

        if code == 0:
            print("  FAILED: an index naming a nonexistent branch audited clean")
            failures += 1
        else:
            print("  ok: an index naming a nonexistent branch fails the audit")

        # The snapshot guard: silent when the count holds, loud when it drops, and
        # never writing into the real history while doing it.
        with tempfile.TemporaryDirectory() as hist:
            store = Path(hist)
            quiet = snapshot_index(idx, 12, history=store)
            dropped = snapshot_index(idx, 3, history=store)
            if quiet:
                print(f"  FAILED: a first snapshot reported {quiet!r}")
                failures += 1
            elif "down from 12" not in dropped:
                print(f"  FAILED: a drop was not reported: {dropped!r}")
                failures += 1
            else:
                print("  ok: the index snapshot is silent on a stable count and loud on a drop")
            if any(store.iterdir()) is False:
                print("  FAILED: no snapshot was written")
                failures += 1

        # The branch-count check: it exists because the index said "Ten branches are
        # prepared" for two rounds while the plan held twelve. Exercise both halves —
        # a wrong number fails, a right one passes, and an unreadable phrasing is a
        # note rather than a silent pass.
        wrong_text = ("> ## ⚠️ Ten branches are prepared, one more was retired\n"
                      "so all 12 are merged into a scratch branch\n")
        wrong_fails, _ = stated_branch_counts(wrong_text, 12)
        if len(wrong_fails) != 1 or "banner" not in wrong_fails[0]:
            print(f"  FAILED: a banner stating the wrong branch count did not fail "
                  f"({wrong_fails})")
            failures += 1
        right_fails, right_notes = stated_branch_counts(
            "> ## ⚠️ Twelve branches are prepared, one more was retired\n"
            "so all 12 are merged into a scratch branch\n", 12)
        if right_fails:
            print(f"  FAILED: a correct index was rejected ({right_fails})")
            failures += 1
        if right_notes:
            print(f"  FAILED: a readable index produced notes ({right_notes})")
            failures += 1
        silent_fails, silent_notes = stated_branch_counts("no counts here at all\n", 12)
        if silent_fails or not silent_notes:
            print(f"  FAILED: an unreadable index passed silently "
                  f"({silent_fails} / {silent_notes})")
            failures += 1

        # Test integrity: both detectors that shipped in the first prototype produced a
        # false positive on the real branches, so both are pinned here by the exact line
        # that fooled them. A rename is not a deletion; `process.exit(` is not `xit(`.
        rename = 'it(\'offers "none" plus the four CLI agents\', () => {'
        if TEST_JS_DEF.search("\n" + rename) is None:
            print("  FAILED: a renamed `it(` was not counted at all")
            failures += 1
        if TEST_SKIP.search("process.exit(failures ? 1 : 0);"):
            print("  FAILED: `process.exit(` was read as a skipped test")
            failures += 1
        if not TEST_SKIP.search("  it.skip('temporarily', () => {})"):
            print("  FAILED: a real `.skip(` was not detected")
            failures += 1
        if not TEST_SKIP.search("@pytest.mark.skip(reason='flake')"):
            print("  FAILED: a real `@pytest.mark.skip` was not detected")
            failures += 1
        if test_definitions("def test_a():\n    assert 1\n", "tests/test_x.py") != 1:
            print("  FAILED: a python test definition was not counted")
            failures += 1

    # End to end, on a throwaway repository: a branch that deletes a test must be caught,
    # and a branch that only adds one must not be. A detector proved only on strings is
    # the kind of check this workspace has already shipped once and regretted.
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        base_test = "def test_one():\n    assert 1\n\n\ndef test_two():\n    assert 2\n"
        (repo / "tests").mkdir()
        (repo / "tests" / "test_x.py").write_text(base_test)
        for argv in (["init", "-q", "-b", "main"], ["add", "-A"],
                     ["-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "base"]):
            subprocess.run(["git", "-C", str(repo), *argv], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "drops"],
                       capture_output=True)
        (repo / "tests" / "test_x.py").write_text("def test_one():\n    assert 1\n")
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                        "commit", "-qam", "drop a test"], capture_output=True)
        caught, _, _ = test_integrity(str(repo), "drops")
        if not any("removed" in f for f in caught):
            print(f"  FAILED: a deleted test was not caught ({caught})")
            failures += 1
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "adds"],
                       capture_output=True)
        (repo / "tests" / "test_x.py").write_text(base_test + "\n\ndef test_three():\n    assert 3\n")
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                        "commit", "-qam", "add a test"], capture_output=True)
        clean, _, _ = test_integrity(str(repo), "adds")
        if clean:
            print(f"  FAILED: a branch that only added a test was rejected ({clean})")
            failures += 1
        # A file the branch CREATED has no baseline, so its tests are not "removed" when
        # the count is lower — pin that, because it is the correct reading of the claim
        # and a careless tightening of the rule would turn it into a false positive.
        # (Checked live too: deleting an `it()` from the chat branch's own new
        # composer.test.ts is silent, while deleting one from datetime.test.ts, which
        # exists on main, reports `1 test(s) removed (12 -> 11)`.)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "newfile"],
                       capture_output=True)
        (repo / "tests" / "test_new.py").write_text(
            "def test_only():\n    assert 1\n")
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                        "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                        "commit", "-qm", "new test file"], capture_output=True)
        newfile, _, _ = test_integrity(str(repo), "newfile")
        if newfile:
            print(f"  FAILED: a newly created test file was read as a removal ({newfile})")
            failures += 1

        # Diff hygiene END TO END, on the same throwaway repository. The parsers above are
        # unit-tested, and that was not enough: a mutant that replaced the call site
        # `for path in parse_binary_files(numstat)` with an empty list passed the whole
        # self-test, because nothing exercised diff_hygiene() itself. A check is only as
        # good as the wiring its test actually touches.
        def commit_new_branch(name: str) -> None:
            """From `main` with the working-tree change already made, commit it on a branch.

            The first version pre-created the branch and then called this, so the second
            `checkout -b` failed silently and the change was committed to `main` instead —
            which made the mode-change case report nothing and look like a broken detector.
            `core.fileMode=true` is explicit because a global `false` would drop the bit.
            """
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"],
                           capture_output=True)
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", name],
                           capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "core.fileMode=true", "add", "-A"],
                           capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b",
                            "-c", "user.name=t", "commit", "-qm", name], capture_output=True)

        (repo / "blob.bin").write_bytes(bytes(range(256)))
        commit_new_branch("binary")
        binary_fails, _ = diff_hygiene(str(repo), "binary")
        if not any("binary" in f for f in binary_fails):
            print(f"  FAILED: a binary file in the diff was not caught ({binary_fails})")
            failures += 1

        # `git checkout main` already removed the committed blob; unlinking it again was
        # a FileNotFoundError the first time this ran.
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"],
                       capture_output=True)
        os.chmod(repo / "tests" / "test_x.py", 0o755)
        commit_new_branch("mode")
        mode_fails, _ = diff_hygiene(str(repo), "mode")
        if not any("mode" in f for f in mode_fails):
            print(f"  FAILED: an executable-bit change was not caught ({mode_fails})")
            failures += 1
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"],
                       capture_output=True)

        # The runbook: a branch that silently fell out of the `--only` batches is the
        # expensive case — the user would ship eleven PRs and be told it all succeeded —
        # so coverage is checked by counting, and the push counts against a stub.
        plan = ["fix/one", "fix/two"]
        good_text = (
            "**2. Push the nine repositories carrying this work — 5 commits.**\n"
            "```bash\n"
            "git -C /home/logic/Work/one push origin main     # 3 commits\n"
            "git -C /home/logic/Work/two push origin main     # 2 commits\n"
            "```\n"
            "submit_prepared_work.py --execute --only fix/one --only fix/two\n")
        stub = lambda _p, _b: 3 if str(_p).endswith("/one") else 2
        clean_fails, _ = runbook_facts(good_text, plan, pathlib.Path("/tmp"), HERE, counter=stub)
        if clean_fails:
            print(f"  FAILED: a correct runbook was rejected ({clean_fails})")
            failures += 1

        dropped = good_text.replace(" --only fix/two", "")
        drop_fails, _ = runbook_facts(dropped, plan, pathlib.Path("/tmp"), HERE, counter=stub)
        if not any("fix/two" in f and "never" in f for f in drop_fails):
            print(f"  FAILED: a branch missing from the runbook was not caught ({drop_fails})")
            failures += 1

        stale = good_text.replace("— 5 commits", "— 99 commits").replace("# 3 commits",
                                                                       "# 30 commits")
        stale_fails, _ = runbook_facts(stale, plan, pathlib.Path("/tmp"), HERE, counter=stub)
        if not any("30 commits" in f for f in stale_fails):
            print(f"  FAILED: a stale per-repo count was not caught ({stale_fails})")
            failures += 1
        if not any("99" in f for f in stale_fails):
            print(f"  FAILED: a stale total was not caught ({stale_fails})")
            failures += 1

        alien_fails, _ = runbook_facts(
            good_text + "--only fix/never-prepared\n", plan, pathlib.Path("/tmp"), HERE,
            counter=stub)
        if not any("never-prepared" in f for f in alien_fails):
            print(f"  FAILED: a branch outside the plan was accepted ({alien_fails})")
            failures += 1

        # A tool the runbook invokes but which does not exist. Anchored on the tools
        # directory: the first version of this matched any `name.py` in prose and invented
        # six missing tools out of repository filenames.
        ghost_fails, _ = runbook_facts(
            good_text + ("python3 \"${DSH_HOME}/.agent-presets/laya-contributor/tools/"
                         "no_such_tool.py\"\n"), plan, pathlib.Path("/tmp"), HERE,
            counter=stub)
        if not any("no_such_tool.py" in f for f in ghost_fails):
            print(f"  FAILED: an invoked tool that does not exist was accepted ({ghost_fails})")
            failures += 1
        prose_fails, _ = runbook_facts(
            good_text + "The suite lives in `engine/tests/conftest.py`.\n", plan,
            pathlib.Path("/tmp"), HERE, counter=stub)
        if prose_fails:
            print(f"  FAILED: a repository path in prose was read as a missing tool "
                  f"({prose_fails})")
            failures += 1
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "skips"],
                       capture_output=True)
        (repo / "tests" / "test_x.py").write_text(
            "import pytest\n\n\n@pytest.mark.skip(reason='x')\ndef test_one():\n    assert 1\n"
            + base_test.split("\n\n\n", 1)[1])
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                        "commit", "-qam", "skip a test"], capture_output=True)
        skipped, _, _ = test_integrity(str(repo), "skips")
        if not any("skip marker" in f for f in skipped):
            print(f"  FAILED: an added skip marker was not caught ({skipped})")
            failures += 1

    # Diff hygiene, pinned by the false positive that produced it: an ADDED file reads
    # `:000000 100644 … A`, and comparing the modes without reading the status column
    # reported eleven phantom "mode changes" across the real branches.
    add_line = ":000000 100644 aaaa bbbb A\tengine/tests/new_test.py"
    mod_line = ":100644 100755 aaaa bbbb M\tscripts/run.sh"
    del_line = ":100644 000000 aaaa bbbb D\tengine/old.py"
    same_line = ":100644 100644 aaaa bbbb M\tengine/same.py"
    if parse_mode_changes(add_line + "\n"):
        print("  FAILED: an added file was read as a mode change")
        failures += 1
    if parse_mode_changes(del_line + "\n"):
        print("  FAILED: a deleted file was read as a mode change")
        failures += 1
    if parse_mode_changes(same_line + "\n"):
        print("  FAILED: an unchanged mode was read as a mode change")
        failures += 1
    if not parse_mode_changes(mod_line + "\n"):
        print("  FAILED: a real mode change was not detected")
        failures += 1
    if parse_binary_files("12\t3\tengine/a.py\n-\t-\tui/logo.png\n") != ["ui/logo.png"]:
        print("  FAILED: a binary file was not detected from numstat")
        failures += 1
    check_fails, check_notes = classify_diff_check(
        "engine/x.py:12: new blank line at EOF.\n")
    if check_fails or not check_notes:
        # No upstream job reads whitespace, so this is a note, never a failure.
        print(f"  FAILED: a whitespace nit was treated as a failure ({check_fails})")
        failures += 1
    conflict_fails, _ = classify_diff_check("engine/x.py:3: leftover conflict marker")
    if not conflict_fails:
        print("  FAILED: a committed conflict marker was not a failure")
        failures += 1

    # The index's own counts. Proven against the two failures that matter: a branch figure
    # that disagrees with its measurement, and a composed figure no run recorded. Both were
    # checked live too — replacing the composed `1211 passed` with 9999 turned the audit red,
    # naming the figure and the run it was compared against.
    manifest = {"entries": {"a|fix/x|engine": {"branch": "fix/x", "suite": "engine",
                                               "green": True, "figures": {"passed": 111}}}}
    composed = {"generated": "T", "ok": True, "records": [
        {"clone": "laya-inspect", "branches": ["b1", "b2"],
         "combined": "7 files changed, 70 insertions(+), 7 deletions(-)",
         "checks": [{"label": "engine suite", "status": "PASS", "detail": "111 passed in 1s"}]},
    ]}
    good = ("| Branch | `fix/x` |\n| Verified | engine **111 passed** = 1 + 1 |\n"
            "## The composed set\n"
            "| merge | **2/2, no conflicts**; `laya-inspect` combined "
            "**7 files changed, +70 / −7** |\n"
            "| engine | **111 passed** (1 s) |\n")
    ok_fails, ok_notes = index_figure_claims(good, manifest, composed)
    if ok_fails:
        print(f"  FAILED: a correct index was rejected ({ok_fails})")
        failures += 1
    bad_branch = good.replace("engine **111 passed**", "engine **999 passed**")
    branch_fails, _ = index_figure_claims(bad_branch, manifest, composed)
    if not any("999" in f and "fix/x" in f for f in branch_fails):
        print(f"  FAILED: a branch figure disagreeing with its measurement was accepted "
              f"({branch_fails})")
        failures += 1
    bad_composed = good.replace("**111 passed** (1 s)", "**4321 passed** (1 s)")
    comp_fails, _ = index_figure_claims(bad_composed, manifest, composed)
    if not any("4321" in f for f in comp_fails):
        print(f"  FAILED: a composed figure no run recorded was accepted ({comp_fails})")
        failures += 1
    bad_stat = good.replace("+70 / −7", "+700 / −7")
    stat_fails, _ = index_figure_claims(bad_stat, manifest, composed)
    if not any("700" in f for f in stat_fails):
        print(f"  FAILED: a diffstat disagreeing with the recorded composition was accepted "
              f"({stat_fails})")
        failures += 1
    bad_merge = good.replace("**2/2, no conflicts**", "**9/9, no conflicts**")
    merge_fails, _ = index_figure_claims(bad_merge, manifest, composed)
    if not any("9" in f for f in merge_fails):
        print(f"  FAILED: a merge count disagreeing with the recorded run was accepted "
              f"({merge_fails})")
        failures += 1
    # No composed record at all must be a NOTE, not a silent pass and not a failure.
    none_fails, none_notes = index_figure_claims(good, manifest, None)
    if none_fails or not none_notes:
        print(f"  FAILED: a missing composed record was not surfaced as a note "
              f"({none_fails} / {none_notes})")
        failures += 1

    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--offline", action="store_true", help="skip the upstream freshness check")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the audit reports a bad index, without checking real work")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    index = Path(args.index)
    audit = Audit()
    print(f"audit: {index}")
    if not index.is_file():
        print(f"  FAIL  index missing: {index}")
        return 1

    claims = parse_claims(index)
    audit.check("index documents prepared branches", len(claims) >= 4, f"{len(claims)} claims parsed")
    # How many branches the index SAYS are prepared, against how many the plan holds.
    # The set grew from ten to twelve and the prose did not follow it twice over.
    size = plan_size()
    if size:
        count_fails, count_notes = stated_branch_counts(
            index.read_text(encoding="utf-8"), size)
        audit.check("index states the current branch count", not count_fails,
                    "; ".join(count_fails) or f"agrees with the plan ({size})")
        for note in count_notes:
            audit.note(note)
    else:
        audit.note("could not read the submission plan, so the index's stated branch "
                   "count was not checked")
    # Snapshot the REAL index before anything else can rewrite it, and shout if the
    # count fell. Gated on the default path so a `--index` run against a scratch or
    # synthetic file cannot write into the history the next real run compares to.
    if index.resolve() == DEFAULT_INDEX.resolve():
        index_note = snapshot_index(index, len(claims))
        if index_note:
            audit.note(index_note)
    if not claims:
        return 1
    for claim in claims:
        print(f"\n  [{claim['section']}] {claim['branch']}")

    repos = sorted({claim["repo"] for claim in claims})
    print("\nbranch + commit verification")
    for claim in claims:
        repo = claim["repo"]
        if not Path(repo, ".git").exists():
            audit.check(f"{claim['branch']}: repo present", False, repo)
            continue
        code, head = run(["git", "-C", repo, "rev-parse", "--verify", claim["branch"]])
        ok = code == 0 and head.startswith(claim["head"])
        audit.check(f"{claim['branch']}: exists at {claim['head']}", ok, head if code == 0 else "branch absent")

    # The runbook the user follows: every prepared branch must appear in an `--only`
    # exactly once, and the commit counts beside each push must be the current ones.
    if size:
        runbook_text = index.read_text(encoding="utf-8")
        plan_branches = plan_branch_names()
        if plan_branches:
            rb_fails, rb_notes = runbook_facts(runbook_text, plan_branches, DEFAULT_WORK_DIR,
                                               pathlib.Path(__file__).resolve().parent)
            audit.check("the runbook would submit every prepared branch", not rb_fails,
                        "; ".join(rb_fails) or f"all {len(plan_branches)} named once, and the "
                                               f"push counts match")
            for note in rb_notes:
                audit.note(note)
        else:
            audit.note("could not read the plan's branch names, so the runbook was not checked")

    # What the index itself claims about the prepared work, against what was measured.
    manifest_path = DEFAULT_WORK_DIR / "prepared-counts.json"
    composed_path = DEFAULT_WORK_DIR / "composed-counts.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    try:
        composed = json.loads(composed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        composed = None
    fig_fails, fig_notes = index_figure_claims(index.read_text(encoding="utf-8"), manifest,
                                               composed)
    audit.check("the index's own counts match what was measured", not fig_fails,
                "; ".join(fig_fails) or
                f"every branch and composed figure agrees "
                f"({len(index_branch_claims(index.read_text(encoding='utf-8')))} branch "
                f"claim(s))")
    for note in fig_notes:
        audit.note(note)

    print("\ndiff hygiene (what a reviewer sees before reading a line of the change)")
    for claim in claims:
        hy_fails, hy_notes = diff_hygiene(claim["repo"], claim["branch"])
        audit.check(f"{claim['branch']}: diff is clean", not hy_fails,
                    "; ".join(hy_fails) or "no binary file, mode change or conflict marker")
        for note in hy_notes:
            audit.note(f"{claim['branch']}: {note}")

    print("\ntest integrity (a green branch must not have got there by deleting or skipping a test)")
    for claim in claims:
        integrity_fails, integrity_notes, checked = test_integrity(claim["repo"], claim["branch"])
        detail = ("; ".join(integrity_fails) if integrity_fails
                  else (f"{checked} test file(s) changed, none lost a test or gained a skip"
                        if checked else "no test files changed"))
        audit.check(f"{claim['branch']}: tests not weakened", not integrity_fails, detail)
        for note in integrity_notes:
            audit.note(note)

    print("\nindependence (the index claims every branch can be its own PR)")
    for repo in repos:
        repo_claims = [claim for claim in claims if claim["repo"] == repo]
        touched: dict[str, set[str]] = {}
        for claim in repo_claims:
            code, out = run(["git", "-C", repo, "diff", "--name-only", f"main...{claim['branch']}"])
            touched[claim["branch"]] = set(out.splitlines()) if code == 0 else set()
        names = sorted(touched)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                overlap = touched[left] & touched[right]
                label = f"{repo.split('/')[-1]}: {left} vs {right}"
                if not overlap:
                    audit.check(f"{label} disjoint", True,
                                f"{len(touched[left])} / {len(touched[right])} files")
                    continue
                # Disjointness was a PROXY for "each can be its own PR", and it just turned
                # out to be too strict: two changes to one file can be independent (each
                # works standalone on main) and still combine. What the proxy protects
                # against is a conflict, or a branch that needs the other — so a declared
                # pair is verified by merging it, not merely noted.
                declared = ALLOWED_OVERLAP.get(frozenset((left, right)))
                if declared is None:
                    audit.check(f"{label} disjoint", False, ", ".join(sorted(overlap)))
                    continue
                code, out = run(["git", "-C", repo, "merge-tree", "--write-tree", left, right])
                clean = code == 0 and "CONFLICT" not in out
                audit.check(f"{label} merge cleanly ({len(overlap)} shared file(s))", clean,
                            declared if clean else out.strip().splitlines()[-1][:120])

    if len(repos) > 1:
        # The pairwise loop above is per-repo, so two branches in two clones were never
        # compared — which is how a four-file overlap between the chat branch and a
        # tool-references branch went unnoticed until it was checked by hand. File names are
        # comparable across clones of the same upstream, so compare them here.
        print("\ncross-repository overlap")
        per_repo: dict[str, dict[str, set[str]]] = {}
        for repo in repos:
            per_repo[repo] = {}
            for claim in [c for c in claims if c["repo"] == repo]:
                code, out = run(["git", "-C", repo, "diff", "--name-only",
                                 f"main...{claim['branch']}"])
                per_repo[repo][claim["branch"]] = set(out.splitlines()) if code == 0 else set()
        names = sorted((repo, b) for repo, branches in per_repo.items() for b in branches)
        for i, (repo_a, left) in enumerate(names):
            for repo_b, right in names[i + 1:]:
                if repo_a == repo_b:
                    continue
                overlap = per_repo[repo_a][left] & per_repo[repo_b][right]
                if not overlap:
                    continue
                label = f"{left} ({Path(repo_a).name}) vs {right} ({Path(repo_b).name})"
                declared = ALLOWED_OVERLAP.get(frozenset((left, right)))
                if declared is None:
                    audit.check(f"{label} overlap", False, ", ".join(sorted(overlap)))
                else:
                    audit.note(f"{label}: {len(overlap)} shared file(s), declared — {declared}")

    if not args.offline:
        print("\nupstream freshness")
        for repo in repos:
            code, local = run(["git", "-C", repo, "rev-parse", "main"])
            code2, remote = run(["git", "-C", repo, "ls-remote", "origin", "refs/heads/main"])
            remote_sha = remote.split()[0] if code2 == 0 and remote else ""
            if not remote_sha:
                audit.note(f"{repo.split('/')[-1]}: upstream unreachable (offline?); merge checks not re-validated")
                continue
            audit.check(f"{repo.split('/')[-1]}: local main == upstream main", local.startswith(remote_sha[:12]) or remote_sha.startswith(local[:12]),
                        f"local {local[:9]} / upstream {remote_sha[:9]}")

    print("\nsafety state (does pytest here destroy the MCP token?)")
    seen: set[str] = set()
    for claim in claims:
        repo = claim["repo"]
        if repo in seen:
            continue
        seen.add(repo)
        code, out = run(["python3", str(CLASSIFIER), "--repo", repo])
        verdict = "UNSAFE" if "UNSAFE" in out else ("SAFE" if "SAFE" in out else "UNKNOWN")
        on_fix = False
        code2, current = run(["git", "-C", repo, "branch", "--show-current"])
        if code2 == 0 and current.strip() == "fix/tests-isolate-laya-home":
            on_fix = True
        if verdict == "UNSAFE":
            audit.note(f"{repo.split('/')[-1]} is UNSAFE and {'MITIGATED (on the fix branch)' if on_fix else 'EXPOSED'}"
                       " — run pytest with HOME=<scratch> LAYA_HOME_IS_SCRATCH=1, or check out the isolation branch")
        else:
            audit.check(f"{repo.split('/')[-1]}: test suite is safe to run", verdict == "SAFE", verdict)

    print("\nremotes (submission footgun: the fork must be wired before any push)")
    for repo in repos:
        code, out = run(["git", "-C", repo, "remote", "-v"])
        wired = "sushant-me" in out
        if wired:
            audit.check(f"{repo.split('/')[-1]}: fork wired as a remote", True)
        else:
            audit.note(f"{repo.split('/')[-1]}: NO fork remote — `git push origin` would target "
                       f"{'the maintainer repo' if UPSTREAM in out else 'a local path'}; run "
                       "'gh repo fork aayushch/laya --clone=false --remote' first")

    total = audit.passed + len(audit.failed)
    verdict = "all green" if not audit.failed else f"{len(audit.failed)} FAILURE(S)"
    # Hazards must appear in the verdict line itself: a reader who skims "all
    # green" must not miss that a tree is UNSAFE or that a fork is unwired.
    hazards = f", {len(audit.notes)} hazard(s) noted" if audit.notes else ""
    print(f"\naudit: {audit.passed}/{total} checks passed — {verdict}{hazards}")
    for failure in audit.failed:
        print(f"  - {failure}")
    for note in audit.notes:
        print(f"  ! {note}")
    return 0 if not audit.failed else 1


if __name__ == "__main__":
    sys.exit(main())
