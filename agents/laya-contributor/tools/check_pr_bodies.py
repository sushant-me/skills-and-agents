#!/usr/bin/env python3
# Copyright 2026 Aayush Chawla
# SPDX-License-Identifier: Apache-2.0

"""Check what the prepared PR bodies actually claim.

A PR body is the artefact a maintainer reads before the diff, and it is the one
artefact nothing else verifies. Reviewers found two bodies asserting things the
code did not do (`2026-09-25`), and both had been written in good faith — the code
changed afterwards and the prose did not. This is the mechanical part of that check:

  FAIL  a repo-relative path named in backticks is not in the branch's tree
  note  a code-shaped identifier named in backticks appears nowhere in the branch
        (often fine — a body may name a symbol it *removed* — so this asks for a
        look rather than failing)
  list  every "N passed" figure per body, so the counts can be compared in one
        place instead of hunted across twelve files
  FAIL  a quoted "N passed" that no measurement supports, or that belongs to a
        different branch the body does not name (see `--require-counts`)

The count check reads `prepared-counts.json`, written by `measure_prepared_counts.py`,
which actually runs each branch's suite in a throwaway worktree. That split is
deliberate: the numbers are earned by a run, never typed here, and this check stays
fast enough for the battery. Three real defects came from a number nothing derived —
a body quoting another branch's `1093`, "Six unit tests" where seven were added, and
`58 tests` published for a suite that collects 60 — so the rule is narrow and
mechanical: a figure must be this branch's, or another branch's *named* in the body.

Usage:
    python3 check_pr_bodies.py [--work-dir /home/logic/Work]
    python3 check_pr_bodies.py --require-counts      # used by the battery
    python3 check_pr_bodies.py --self-test
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_WORK_DIR = pathlib.Path.home() / "Work"
# Written by measure_prepared_counts.py. Absent is not an error on a bare run — it is
# an error under --require-counts, which is how the battery enforces the cross-check
# instead of a missing manifest quietly turning the check off.
DEFAULT_COUNTS = DEFAULT_WORK_DIR / "prepared-counts.json"
# The label `measure_prepared_counts.py` gives the base tree, whose count a body may
# legitimately quote as context rather than as a claim of its own.
BASE_LABEL = "main"

# Backticked tokens that look like a repo path but are not one.
NON_PATH_PREFIXES = ("/", "~", "http://", "https://", "ws://", "tauri://")
# `POST /cards/read-all` contains a slash and is not a path. Neither is a status
# pair like `HIGH/ready`, and neither is a branch name.
HTTP_METHOD = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s")
BRANCH_PREFIX = re.compile(r"^(fix|feat|test|chore|docs|release|revert)/")
COUNT_CLAIM = re.compile(r"(\d{3,5})\s+passed")

# A backticked identifier worth looking for in the tree: it reads as code rather
# than as prose. `main`, `recent`, `state` and friends are excluded by requiring an
# underscore or an inner capital.
IDENTIFIER = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{4,})`")
PROSE_ALLOW = {"github", "python", "tauri", "svelte", "pytest", "vitest", "npm", "json"}

# Artifacts that are NOT submission-plan PR bodies but are still read by someone
# outside this workspace: (path, clone, the branch whose code they describe).
# The #13 reply was written across several rounds and its route list had to be
# corrected once — exactly the drift this checks for.
EXTRA_ARTIFACTS = (
    ("laya-issue-13-reply.md", "laya-inspect", "main"),
)

# ── HTTP route claims ───────────────────────────────────────────────────────
# A body that names a route can name one that does not exist: the first draft of
# the cross-site PR called `POST /prompts/reload` by the path
# `POST /settings/prompts/reload`. Nothing checked that, so this does — statically,
# from the branch's own decorators, because importing twelve branches' apps is slow
# and runs their module-level code.
ROUTE_METHOD = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/\S*)$")
ROUTE_DECORATOR = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete|head|options)\(\s*[\"']([^\"']*)[\"']")
ROUTER_PREFIX = re.compile(r"APIRouter\([^)]*?prefix\s*=\s*[\"']([^\"']*)[\"']", re.S)
IMPORT_AS = re.compile(r"from\s+laya\.api\.(\w+)\s+import\s+router\s+as\s+(\w+)")
INCLUDE = re.compile(r"include_router\(\s*([A-Za-z_]\w*)\s*(?:,\s*prefix\s*=\s*[\"']([^\"']*)[\"'])?")
MODEL_CLASS = re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)\s*:", re.M)


def _normalize_route(method: str, path: str) -> tuple[str, str]:
    """`DELETE /cards/{id}` and `/cards/{card_id}` are the same route."""
    shape = re.sub(r"\{[^}]*\}", "{}", path.rstrip("/") or "/")
    return method.upper(), shape


def declared_routes(sources: dict[str, str]) -> dict[tuple[str, str], bool]:
    """{(METHOD, path-shape): takes_a_request_body} from a branch's own source.

    `sources` maps repo-relative path -> file text, so this stays pure and can be
    tested without git. The body flag is a static read of the handler's signature:
    an annotation that names a `BaseModel` subclass defined in the same file, or a
    `Body(...)` default. A model imported from elsewhere is missed, which errs
    towards *not* warning — a false "takes a body" would be worse than silence here,
    because it would invite someone to dismiss a real finding.
    """
    routes: dict[tuple[str, str], bool] = {}
    # app-level prefixes for included routers, e.g. include_router(x, prefix="/v1")
    app_prefix: dict[str, str] = {}
    main = next((t for p, t in sources.items() if p.endswith("main.py")), "")
    alias_to_module = {alias: mod for mod, alias in IMPORT_AS.findall(main)}
    for alias, prefix in INCLUDE.findall(main):
        if alias in alias_to_module:
            app_prefix[alias_to_module[alias]] = prefix

    for path, text in sources.items():
        is_engine_source = path.endswith("main.py") or (
            path.endswith(".py") and "/api/" in path)
        if not is_engine_source:
            continue
        module = path.rsplit("/", 1)[-1][:-3]
        match = ROUTER_PREFIX.search(text)
        prefix = app_prefix.get(module, "") + (match.group(1) if match else "")
        models = {name for name, bases in MODEL_CLASS.findall(text) if "BaseModel" in bases}
        for method, decorator_path in ROUTE_DECORATOR.findall(text):
            takes_body = False
            # Read the handler that follows this decorator. A window of lines, not
            # "up to the first colon": the signature's first annotation colon
            # truncated it, so `def f(a: str, body: ActiveRequest)` read as if it took
            # no body at all — which is exactly the mistake this check exists for.
            tail = text.split(f'"{decorator_path}"', 1)[-1]
            head = "\n".join(tail.splitlines()[:6])
            if "Body(" in head:
                takes_body = True
            elif models and any(m in head for m in models):
                takes_body = True
            routes[_normalize_route(method, prefix + decorator_path)] = takes_body
    return routes


def ui_page_routes(files: list[str]) -> set[str]:
    """SvelteKit page paths, e.g. `ui/src/routes/chat/+page.svelte` -> `/chat`.

    A body may legitimately name a *page* route (`GET /chat` is the full-page chat),
    which is not an engine route at all — the first live run of this check reported
    exactly that as missing.
    """
    found = set()
    marker = "ui/src/routes/"
    for name in files:
        if marker in name and name.endswith("/+page.svelte"):
            tail = name.split(marker, 1)[1][: -len("/+page.svelte")]
            if tail:
                found.add("/" + re.sub(r"\[[^\]]*\]", "{}", tail))
    return found


def is_path_claim(token: str, known_branches: set[str], top_level: set[str]) -> bool:
    """Is this backticked token a claim about a file in the repository?

    The first segment has to be a real top-level entry of the branch. That single
    rule removes the three things that are *not* paths but look exactly like them —
    an HTTP route, a `HIGH/ready` status pair, and a branch name — without listing
    any of them: a body may say `POST /cards/read-all`, but no branch has a
    top-level `POST`, and no branch has a top-level `fix`.
    """
    if "/" not in token or token.startswith(NON_PATH_PREFIXES):
        return False
    if HTTP_METHOD.match(token) or token in known_branches or BRANCH_PREFIX.match(token):
        return False
    return token.split("/", 1)[0] in top_level


def is_code_identifier(token: str) -> bool:
    if token.lower() in PROSE_ALLOW or token.isupper():
        return False
    return "_" in token or any(ch.isupper() for ch in token[1:])


def check_body_text(body_text: str, files: list[str], tree_text: str,
                    known_branches: set[str],
                    elsewhere: frozenset[str] = frozenset(),
                    exists_on_disk=None,
                    routes: dict[tuple[str, str], bool] | None = None,
                    pages: set[str] | None = None,
                    ) -> tuple[list[str], list[str], list[str]]:
    """(failures, notes, count_figures) for one body. Pure: no git, no disk.

    `elsewhere` is the union of paths in the *other* prepared branches, and
    `exists_on_disk` answers whether a path is present but untracked (a gitignored
    build directory, say). Both downgrade a FAIL to a note, because a body may
    legitimately name either — the retired-pin branch's test file, or `ui/node_modules`
    — and a FAIL here has to mean "this exists nowhere at all".

    `routes` is `declared_routes(...)` for this branch. A backticked `METHOD /path`
    must be declared, and if it takes a request body that is said out loud: a body
    that offers it as reachable from a cross-site page would otherwise be claiming
    something a CORS preflight prevents.
    """
    exists_on_disk = exists_on_disk or (lambda _token: False)
    routes = routes or {}
    pages = pages or set()
    basenames = {f.rsplit("/", 1)[-1] for f in files}
    top_level = {f.split("/", 1)[0] for f in files}
    failures: list[str] = []
    notes: list[str] = []

    backticked = re.findall(r"`([^`\n]+)`", body_text)

    for raw in backticked:
        claim = ROUTE_METHOD.match(raw.strip())
        if not claim:
            continue
        key = _normalize_route(claim.group(1), claim.group(2))
        if key not in routes:
            if key[1] in pages:
                continue          # a page route, not an engine route: fine
            failures.append(f"route `{raw.strip()}` is not declared by this branch")
        elif routes[key]:
            notes.append(f"route `{raw.strip()}` takes a request body, so a cross-site "
                         f"simple request cannot reach it — check the claim around it")

    candidates = set()
    for raw in backticked:
        # `path.py::test_name` is a claim about the path, so judge the path.
        token = raw.split("::", 1)[0].strip()
        if is_path_claim(token, known_branches, top_level):
            candidates.add(token)

    for token in sorted(candidates):
        # A glob names a set of files ("the n8n ingestion workflows"), so it is
        # satisfied when anything matches — and it is a claim worth checking, because
        # a pattern that matches nothing is a body pointing at files that are gone.
        if any(ch in token for ch in "*?["):
            if any(fnmatch.fnmatch(f, token) for f in files):
                continue
            failures.append(f"path pattern `{token}` matches no file in the branch")
            continue
        if token in files or token.rsplit("/", 1)[-1] in basenames:
            continue
        if any(f.startswith(token) for f in files):   # a directory, e.g. `api/`
            continue
        if token in elsewhere:
            notes.append(f"path `{token}` is not in this branch but is in another "
                         f"prepared branch — confirm the body means that one")
            continue
        if exists_on_disk(token):
            notes.append(f"path `{token}` is present but not tracked by git "
                         f"(a gitignored artefact?) — confirm it is meant as a local path")
            continue
        failures.append(f"path `{token}` is not in the branch")

    for token in sorted({m for m in IDENTIFIER.findall(body_text)
                         if is_code_identifier(m)}):
        if token not in tree_text:
            notes.append(f"`{token}` appears nowhere in the branch — confirm the body "
                         f"describes it as removed rather than as current")

    counts = sorted({f"{n} passed" for n in COUNT_CLAIM.findall(body_text)},
                    key=lambda c: int(c.split()[0]))
    return failures, notes, counts


def _git(clone: pathlib.Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(clone), *args],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (out.stdout or "").strip()


def branch_files(clone: pathlib.Path, branch: str) -> list[str]:
    return _git(clone, "ls-tree", "-r", "--name-only", branch).splitlines()


def local_branches(clone: pathlib.Path) -> list[str]:
    out = _git(clone, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [b for b in out.splitlines() if b]


def branch_text(clone: pathlib.Path, branch: str) -> str:
    chunks = []
    for name in branch_files(clone, branch):
        if name.endswith((".py", ".rs", ".ts", ".js", ".svelte", ".md", ".json",
                          ".mjs", ".sh", ".sql", ".toml", ".yml")):
            chunks.append(_git(clone, "show", f"{branch}:{name}"))
    return "\n".join(chunks)


def branch_sources(clone: pathlib.Path, branch: str) -> dict[str, str]:
    """Only the files that can declare a route: the app and its api modules."""
    out: dict[str, str] = {}
    for name in branch_files(clone, branch):
        if name.endswith("main.py") or (name.endswith(".py") and "/api/" in name):
            out[name] = _git(clone, "show", f"{branch}:{name}")
    return out


def manifest_requirement(path: pathlib.Path, measurements: int,
                         required: bool) -> str | None:
    """Why the run must stop, or None.

    Split out of `main` because `--self-test` returns before argument parsing, so this
    rule — the one that makes a *missing* measurement manifest a failure rather than a
    silent pass — was the single part of this checker no test could reach. Disabling it
    passed the whole self-test.
    """
    if measurements or not required:
        return None
    return (f"no measurements in {path}; run measure_prepared_counts.py, or the count "
            f"claims in every body go unchecked")


def _counts_module():
    """`measure_prepared_counts` as a module, so both readers share one migration.

    This checker reads the manifest itself, which is how it could keep accepting a figure
    the measuring tool had already superseded — two readers of one file, and only one of
    them knew the key format had changed. Same shape as every other two-reader bug here.
    """
    spec = importlib.util.spec_from_file_location(
        "_mpc_for_counts", HERE / "measure_prepared_counts.py")
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:                                            # noqa: BLE001
        return None
    return module


def load_counts(path: pathlib.Path) -> tuple[dict[str, set[int]], dict[int, set[str]],
                                             dict[int, set[str]], int, list[str],
                                             dict[int, str]]:
    """(figures per branch, owner branches per figure, variant labels per figure, count).

    Only a *green* run's figure is indexed: a red run's "1080 passed" is a real
    observation but not something a body should offer as evidence, and indexing it
    would make a stale claim look measured. A branch with no green measurement is
    simply absent, which the caller reports rather than papers over.

    Variant entries are indexed separately. A counterfactual — "the same tree with the
    two new tests removed is 246" — is a legitimate thing for a body to state, and it is
    measured by the same tool with `--variant-label`; keeping it in its own index means
    it can be recognised without ever being confused for the branch's own figure.
    """
    by_branch: dict[str, set[int]] = {}
    owners: dict[int, set[str]] = {}
    variants: dict[int, set[str]] = {}
    notes: list[str] = []
    base_commits: dict[int, str] = {}
    measurements = 0
    if not path.is_file():
        return by_branch, owners, variants, 0, notes, base_commits
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return by_branch, owners, variants, 0, notes, base_commits
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return by_branch, owners, variants, 0, notes, base_commits
    module = _counts_module()
    if module is not None:
        notes = module.migrate_legacy_keys(data, path)
    for entry in entries.values():
        if not isinstance(entry, dict) or not entry.get("figures"):
            continue
        measurements += 1
        passed = entry["figures"].get("passed")
        if not isinstance(passed, int):
            continue
        if entry.get("variant"):
            # A counterfactual is indexed whether or not it was green, because a
            # mutation that turns tests red is the *point* of some of them: reverting
            # the cursor test file yields "2 failed, 244 passed", which is evidence the
            # branch's registry change is covered. The redness travels with the label so
            # the note cannot read as if the branch tip were red.
            label = str(entry["variant"])
            if not entry.get("green"):
                not_passing = entry["figures"].get("not_passed")
                label += (f" — that run was red on purpose: {not_passing} not passing"
                          if not_passing else " — that run was not green")
            variants.setdefault(passed, set()).add(label)
            continue
        if not entry.get("green"):
            continue
        by_branch.setdefault(entry.get("branch", "?"), set()).add(passed)
        owners.setdefault(passed, set()).add(entry.get("branch", "?"))
        if entry.get("branch") == BASE_LABEL and entry.get("sha"):
            # `main` moves, so "the base tree's count" is ambiguous without the commit.
            base_commits.setdefault(passed, entry["sha"][:8])
    return by_branch, owners, variants, measurements, notes, base_commits


def judge_counts(body_text: str, branch: str,
                 by_branch: dict[str, set[int]],
                 owners: dict[int, set[str]],
                 variants: dict[int, set[str]] | None = None,
                 base_commits: dict[int, str] | None = None) -> tuple[list[str], list[str]]:
    """(failures, notes) for every "N passed" the body quotes.

    The rule is deliberately narrow, because the alternative — trying to read prose —
    is how a checker starts producing confident nonsense. A figure is fine when it is
    this branch's own, and fine when it belongs to another branch the body names
    (`feat/omni-open-items-input` in the isolation body, for a concurrency experiment
    run there). Anything else is a FAIL: that is the exact shape of the defect this
    exists for. A figure no branch has measured is a note, because it may come from a
    suite the manifest does not cover yet — and an unmeasured number does not become
    a passing one.
    """
    variants = variants or {}
    base_commits = base_commits or {}
    failures: list[str] = []
    notes: list[str] = []
    mine = by_branch.get(branch, set())
    for figure in sorted({int(n) for n in COUNT_CLAIM.findall(body_text)}):
        if figure in mine:
            continue
        own = owners.get(figure)
        if not own:
            labels = sorted(variants.get(figure, ()))
            if labels:
                notes.append(f"count `{figure} passed` was measured as a counterfactual "
                             f"({labels[0]}) — confirm the body describes it that way")
            else:
                notes.append(f"count `{figure} passed` is no measured branch tip — if it "
                             f"is a counterfactual (a run with a change reverted) or an "
                             f"earlier revision's figure, say so where it is quoted; "
                             f"otherwise treat it as stale")
            continue
        # A figure the base tree also measured is context a body is right to give
        # ("main is 1074 passed"), not a claim about this branch. Two reasons it is
        # exempt rather than failing: `main` is an ordinary English word, so "the body
        # names it" would be satisfied by any prose at all; and a branch that adds no
        # tests measures the same figure as the base (`fix/dev-requirements` is exactly
        # that), so ownership is shared and attribution would be a guess. Both are
        # notes. The FAIL branch below is kept for a figure the base tree does NOT have,
        # which is the shape of the real defect (1093, measured on a sibling branch).
        if BASE_LABEL in own:
            where = base_commits.get(figure)
            notes.append(f"count `{figure} passed` is `{BASE_LABEL}`"
                         f"{f' at {where}' if where else ''} — context rather than a claim "
                         f"about this branch")
            continue
        siblings = sorted(own)
        named = [b for b in siblings if b in body_text]
        if named:
            notes.append(f"count `{figure} passed` is {named[0]}'s, which the body names "
                         f"— confirm that is the intent")
            continue
        failures.append(f"count `{figure} passed` is not this branch's measured count; "
                        f"it belongs to {', '.join(siblings)}, which the body does "
                        f"not name (this branch measured: "
                        f"{', '.join(str(f) for f in sorted(mine)) or 'nothing yet'})")
    return failures, notes


def plan_rows() -> list[tuple[str, str, str]]:
    spec = importlib.util.spec_from_file_location(
        "_spw_for_bodies", HERE / "submit_prepared_work.py")
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [(branch, clone, body) for branch, clone, body, _d in module.PLAN]


# ── the PR title ────────────────────────────────────────────────────────────
# The title is the most-read line of a submission and it is not written anywhere: the
# submit tool takes it from the body's first `# ` heading. Nothing printed it, so nothing
# noticed that one body's title carried `**bold**` — GitHub renders only backtick code
# spans in titles (it added that in 2021 and nothing else), so the asterisks would have
# appeared literally in the pull request list.
TITLE_UNSUPPORTED = {"**": "bold", "__": "bold", "](": "a link", "~~": "strikethrough"}
TITLE_TYPE_PREFIX = re.compile(r"^[A-Z][a-z]+:\s")
TITLE_MAX_CHARS = 100


def body_title(text: str) -> str:
    """The title the submit tool will use: the first `# ` heading."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def judge_titles(titles: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """(failures, notes) for every title in the set. `titles` is (branch, text).

    Two mechanical rules, both from real behaviour rather than taste: markdown GitHub
    does not render in a title must not be there, and a title longer than 100 characters
    is cut off in the pull-request list. Style consistency is a note, not a failure —
    a mixed set is a smell, not a defect, and the honest thing is to say so and let a
    human decide.
    """
    failures: list[str] = []
    notes: list[str] = []
    prefixed = []
    for branch, title in titles:
        if not title:
            failures.append(f"{branch}: the body has no `# ` heading, so the submit tool "
                            f"cannot take a title from it")
            continue
        for marker, what in TITLE_UNSUPPORTED.items():
            if marker in title:
                failures.append(f"{branch}: the title contains `{marker}`, which is {what} "
                                f"and GitHub does not render markdown in titles — it will "
                                f"show literally")
        if len(title) > TITLE_MAX_CHARS:
            failures.append(f"{branch}: the title is {len(title)} characters; GitHub cuts "
                            f"it off in the list at about {TITLE_MAX_CHARS}")
        if TITLE_TYPE_PREFIX.match(title):
            prefixed.append(branch)
    if prefixed and len(prefixed) != len(titles):
        notes.append(f"{len(prefixed)} of {len(titles)} titles use a `Type:` prefix and the "
                     f"rest do not, so the set reads inconsistently: {', '.join(prefixed)}")
    return failures, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=pathlib.Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--counts", type=pathlib.Path, default=DEFAULT_COUNTS,
                        help="the measurement manifest from measure_prepared_counts.py")
    parser.add_argument("--require-counts", action="store_true",
                        help="fail when the manifest is missing or empty, instead of "
                             "noting that the count cross-check did not run")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the checker can fail, without reading the real bodies")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    (by_branch, owners, variants, measurements, migration_notes,
     base_commits) = load_counts(args.counts)
    for note in migration_notes:
        print(f"note: manifest {note}")
    blocked = manifest_requirement(args.counts, measurements, args.require_counts)
    if blocked:
        print(f"FAIL — {blocked}", file=sys.stderr)
        return 1
    if measurements:
        print(f"count manifest: {measurements} measurement(s) from {args.counts}")
    else:
        print(f"note: no count manifest at {args.counts} — quoted figures are listed "
              f"but not cross-checked")

    rows = plan_rows()
    if not rows:
        print("error: could not read the submission plan", file=sys.stderr)
        return 2
    known_branches = {b for b, _, _ in rows}

    # Union of every path on ANY local branch of either clone. A body may name a
    # path that belongs to a sibling branch — the cursor body cites the retired pin
    # branch's test file by name — and that is not a false claim. Restricting this
    # to the plan's branches missed the retired one, which is exactly the case that
    # came up.
    per_branch_files: dict[str, list[str]] = {}
    all_paths: set[str] = set()
    for branch, clone_name, _body in rows:
        per_branch_files[branch] = branch_files(args.work_dir / clone_name, branch)
        all_paths.update(per_branch_files[branch])
    for clone_name in dict.fromkeys(c for _b, c, _d in rows):
        clone = args.work_dir / clone_name
        for other in local_branches(clone):
            all_paths.update(branch_files(clone, other))

    total_fails = 0
    titles: list[tuple[str, str]] = []
    print(f"checking {len(rows)} PR bodies against their branches")
    for branch, clone_name, body_name in rows:
        clone = args.work_dir / clone_name
        body = args.work_dir / body_name
        if not body.is_file():
            print(f"\n{branch}: FAIL — {body} is missing")
            total_fails += 1
            continue
        files = per_branch_files[branch]
        if not files:
            print(f"\n{branch}: FAIL — {branch} is not in {clone}")
            total_fails += 1
            continue
        body_text = body.read_text(encoding="utf-8")
        failures, notes, counts = check_body_text(
            body_text, files, branch_text(clone, branch),
            known_branches,
            elsewhere=frozenset(all_paths - set(files)),
            exists_on_disk=lambda token, c=clone: (c / token).exists(),
            routes=declared_routes(branch_sources(clone, branch)),
            pages=ui_page_routes(files))
        count_fails, count_notes = judge_counts(
            body_text, branch, by_branch, owners, variants, base_commits)
        failures += count_fails
        notes += count_notes
        titles.append((branch, body_title(body_text)))
        print(f"\n{branch}")
        print(f"  counts quoted : {', '.join(counts) if counts else '(none)'}")
        for failure in failures:
            print(f"  FAIL  {failure}")
        for note in notes:
            print(f"  note  {note}")
        if not failures and not notes:
            print("  ok    every path and identifier it names is in the branch")
        total_fails += len(failures)

    # The titles the submit tool will actually use, which nothing printed before.
    print(f"\nPR titles ({len(titles)}), taken from each body's first `# ` heading")
    for branch, title in titles:
        print(f"  {len(title):>3}  {branch:<38} {title}")
    title_fails, title_notes = judge_titles(titles)
    for failure in title_fails:
        print(f"  FAIL  {failure}")
    for note in title_notes:
        print(f"  note  {note}")
    total_fails += len(title_fails)

    checked = [(b, c, w) for b, c, w in rows]
    for artifact, clone_name, branch in EXTRA_ARTIFACTS:
        path = args.work_dir / artifact
        if path.is_file():
            checked.append((artifact, clone_name, branch))

    for artifact, clone_name, branch in checked[len(rows):]:
        clone = args.work_dir / clone_name
        files = branch_files(clone, branch)
        if not files:
            print(f"\n{artifact}: FAIL — {branch} is not in {clone}")
            total_fails += 1
            continue
        artifact_text = (args.work_dir / artifact).read_text(encoding="utf-8")
        failures, notes, counts = check_body_text(
            artifact_text, files,
            branch_text(clone, branch), known_branches,
            elsewhere=frozenset(all_paths - set(files)),
            exists_on_disk=lambda token, c=clone: (c / token).exists(),
            routes=declared_routes(branch_sources(clone, branch)),
            pages=ui_page_routes(files))
        count_fails, count_notes = judge_counts(
            artifact_text, branch, by_branch, owners, variants, base_commits)
        failures += count_fails
        notes += count_notes
        print(f"\n{artifact} (against `{branch}`)")
        print(f"  counts quoted : {', '.join(counts) if counts else '(none)'}")
        for failure in failures:
            print(f"  FAIL  {failure}")
        for note in notes:
            print(f"  note  {note}")
        if not failures and not notes:
            print("  ok    every path, route and identifier it names checks out")
        total_fails += len(failures)

    print()
    if total_fails:
        print(f"{total_fails} claim(s) contradicted by the branch — fix the body, "
              f"not the branch, unless the branch is the thing that is wrong")
        return 1
    print("no body claims a path its branch does not have")
    return 0


def self_test() -> int:
    """Prove it can fail. A check that only ever says 'ok' is decoration."""
    print("self-test: a body naming a path the branch does not have")
    failures = 0
    files = ["engine/laya/api/chat_api.py", "engine/laya/pipeline/chat.py",
             "engine/tests/test_chat_tool_calls.py"]
    tree = "\n".join(files) + "\ntool_call_names\ninsert_test_conversation\n"

    bad_fails, bad_notes, counts = check_body_text(
        "See `engine/laya/api/chat_api.py` and `engine/laya/nope/missing.py`.\n"
        "`tool_call_names` does it. 1085 passed.\n",
        files, tree, {"fix/example"})
    if not any("missing.py" in f for f in bad_fails):
        print(f"  FAILED: a missing path was not reported ({bad_fails})")
        failures += 1
    if bad_notes:
        print(f"  FAILED: a symbol that IS in the tree was reported missing ({bad_notes})")
        failures += 1
    if counts != ["1085 passed"]:
        print(f"  FAILED: count claim not surfaced ({counts})")
        failures += 1

    good_fails, good_notes, _ = check_body_text(
        "`engine/laya/pipeline/chat.py` holds `tool_call_names`.\n", files, tree,
        {"fix/example"})
    if good_fails or good_notes:
        print(f"  FAILED: a clean body was not clean ({good_fails} / {good_notes})")
        failures += 1

    # A branch name contains a slash and must not be mistaken for a path claim.
    branch_fails, _, _ = check_body_text(
        "`fix/dev-requirements` already landed upstream.\n", files, tree,
        {"fix/dev-requirements"})
    if branch_fails:
        print(f"  FAILED: a branch name was read as a path claim ({branch_fails})")
        failures += 1

    # HTTP routes and status pairs contain slashes too. The first revision of this
    # checker reported eleven of them as missing paths in one body.
    route_fails, _, _ = check_body_text(
        "A page could `POST /cards/read-all`, `DELETE /sources/{id}`, and a card "
        "stayed `HIGH/ready`.\n", files, tree, {"fix/example"})
    path_fails = [f for f in route_fails if "is not in the branch" in f]
    if path_fails:
        print(f"  FAILED: an HTTP route or status pair was read as a path ({path_fails})")
        failures += 1

    # A glob is a claim about a set of files, and must be checked as one: the reply
    # cites `n8n/workflows/*-ingestion.json`, and a literal-path reading of that
    # failed on the first run.
    glob_fails, _, _ = check_body_text(
        "See `engine/laya/api/*_api.py` and `engine/laya/api/*_nope.py`.\n",
        files, tree, set())
    if not any("_nope.py" in f for f in glob_fails):
        print(f"  FAILED: a glob matching nothing was not reported ({glob_fails})")
        failures += 1
    if any("_api.py" in f for f in glob_fails):
        print(f"  FAILED: a glob that does match was reported missing ({glob_fails})")
        failures += 1

    # `path.py::test_name` is a claim about the path.
    colon_fails, _, _ = check_body_text(
        "`engine/laya/pipeline/chat.py::tool_call_names` does it.\n", files, tree,
        {"fix/example"})
    if colon_fails:
        print(f"  FAILED: a path with a `::symbol` suffix was misread ({colon_fails})")
        failures += 1

    # A symbol a body names as *removed* is a note, never a failure.
    note_fails, note_notes, _ = check_body_text(
        "The first revision had `_tool_call_names` in two places.\n", files, tree,
        {"fix/example"})
    if note_fails or not note_notes:
        print(f"  FAILED: a removed symbol was treated as a failing claim ({note_fails})")
        failures += 1

    # The title rules, pinned by the defect that produced them: a body whose H1 carried
    # `**bold**`, which GitHub shows literally in a PR title because only backtick code
    # spans render there.
    bold_fails, _ = judge_titles([("fix/a", "Fix: keep the suite out of **the keychain**")])
    if not any("**" in f for f in bold_fails):
        print(f"  FAILED: unsupported markdown in a title was accepted ({bold_fails})")
        failures += 1
    long_fails, _ = judge_titles([("fix/a", "Fix " + "x" * 120)])
    if not any("characters" in f for f in long_fails):
        print(f"  FAILED: an over-long title was accepted ({long_fails})")
        failures += 1
    mixed_fails, mixed_notes = judge_titles([("fix/a", "Fix: one"), ("fix/b", "Fix two")])
    if mixed_fails or not mixed_notes:
        print(f"  FAILED: a mixed title set was not surfaced as a note "
              f"({mixed_fails} / {mixed_notes})")
        failures += 1
    plain_fails, plain_notes = judge_titles([("fix/a", "Keep one"), ("fix/b", "Keep two")])
    if plain_fails or plain_notes:
        print(f"  FAILED: a consistent title set was not clean ({plain_fails} / {plain_notes})")
        failures += 1
    code_fails, _ = judge_titles([("fix/a", "Keep the suite out of `~/.laya`")])
    if code_fails:
        # A backtick code span IS rendered by GitHub in titles; flagging it would be wrong.
        print(f"  FAILED: a backtick code span in a title was rejected ({code_fails})")
        failures += 1
    if body_title("\n# The title\n\ntext\n") != "The title":
        print("  FAILED: the title was not read from the first `# ` heading")
        failures += 1

    # The manifest rule: under --require-counts an absent manifest is a FAILURE, not a
    # note, which is the whole reason the battery passes that flag.
    if manifest_requirement(pathlib.Path("/nonexistent.json"), 0, True) is None:
        print("  FAILED: a missing manifest under --require-counts was not a failure")
        failures += 1
    if manifest_requirement(pathlib.Path("/nonexistent.json"), 0, False) is not None:
        print("  FAILED: a missing manifest failed a plain run")
        failures += 1
    if manifest_requirement(pathlib.Path("/x.json"), 5, True) is not None:
        print("  FAILED: a manifest with measurements was rejected")
        failures += 1

    # The manifest migration, from the reading side. This checker reads the manifest
    # itself, which is how it kept accepting a figure the capturing tool had already
    # superseded — two readers of one file and only one of them knew the key format had
    # changed. It must now migrate before indexing, so the legacy row is not lost and the
    # stale `main` figure does not stand in for a sibling branch.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        legacy_path = pathlib.Path(tmp) / "counts.json"
        legacy_path.write_text(json.dumps({"entries": {
            "fix/x|engine": {"clone": "laya", "branch": "fix/x", "suite": "engine",
                             "sha": "aaaa", "measured_at": "2026-09-25T05:00:00",
                             "green": True, "figures": {"passed": 111}},
        }}), encoding="utf-8")
        by_branch, _owners, _variants, count, notes, _base = load_counts(legacy_path)
        if by_branch.get("fix/x") != {111}:
            print(f"  FAILED: a legacy manifest row was not indexed ({by_branch})")
            failures += 1
        if not any("re-keyed" in n for n in notes):
            # The migration must be visible: a silent re-key is a silent history rewrite.
            print(f"  FAILED: the migration was silent ({notes})")
            failures += 1
        if count != 1:
            print(f"  FAILED: the migrated row was not counted ({count})")
            failures += 1

    failures += _self_test_routes()
    failures += _self_test_counts()
    print("self-test:", "FAILED" if failures else "passed")
    return 1 if failures else 0


def _self_test_counts() -> int:
    """Prove the count cross-check fires, using the defect it was built for.

    The load-bearing case is the third: a body quoting *another* branch's figure
    without naming it is exactly what shipped once (1093 on the isolation branch),
    and a checker that cannot fail on it is decoration. The fourth pins the fix —
    the same figure, the branch named — so the rule cannot be tightened into a
    false positive on the corrected text.
    """
    failures = 0
    by_branch = {"fix/mine": {1081}, "feat/other": {1093}, "main": {1074}}
    owners: dict[int, set[str]] = {}
    for branch, figures in by_branch.items():
        for figure in figures:
            owners.setdefault(figure, set()).add(branch)

    own_fails, own_notes = judge_counts(
        "| engine | `1081 passed` |\n", "fix/mine", by_branch, owners)
    if own_fails or own_notes:
        print(f"  FAILED: this branch's own count was not accepted quietly "
              f"({own_fails} / {own_notes})")
        failures += 1

    # A body quoting the base tree's figure is giving context, not claiming it. That
    # must be a note: the isolation body quotes main's 1074 beside its own 1081.
    base_fails, base_notes = judge_counts("`1074 passed` before this change.\n", "fix/mine",
                                          by_branch, owners)
    if base_fails or not base_notes:
        print(f"  FAILED: a base-tree count was not surfaced as a note ({base_fails})")
        failures += 1

    stray_fails, _ = judge_counts("`1093 passed` for the concurrency run.\n", "fix/mine",
                                  by_branch, owners)
    if not any("feat/other" in f for f in stray_fails):
        print(f"  FAILED: another branch's count was accepted, unnamed ({stray_fails})")
        failures += 1

    named_fails, named_notes = judge_counts(
        "`1093 passed` measured on `feat/other`.\n", "fix/mine", by_branch, owners)
    if named_fails or not named_notes:
        print(f"  FAILED: a named, disclosed count was rejected ({named_fails})")
        failures += 1

    ghost_fails, ghost_notes = judge_counts("`9999 passed`\n", "fix/mine",
                                            by_branch, owners)
    if ghost_fails or not ghost_notes:
        # An unmeasured figure is a note, not a failure: it may come from a suite the
        # manifest does not cover. It must never be silent, though.
        print(f"  FAILED: an unmeasured count was silently accepted ({ghost_fails})")
        failures += 1

    # A counterfactual the tool measured with `--variant-label` is recognised as such,
    # and must never be attributed to a branch: the cursor body's 246 is 248 minus the
    # two tests the fix added, not any branch's own count.
    var_fails, var_notes = judge_counts("`246 passed` with those two tests removed.\n",
                                        "fix/mine", by_branch, owners,
                                        {246: {"two tests removed"}})
    if var_fails or not var_notes or "counterfactual" not in var_notes[0]:
        print(f"  FAILED: a measured counterfactual was not recognised as one "
              f"({var_fails} / {var_notes})")
        failures += 1

    # A red run's figure must not become a quotable measurement, or a stale claim
    # would look measured. The manifest is written to a temp file for this one.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        manifest = pathlib.Path(tmp) / "counts.json"
        manifest.write_text(json.dumps({"entries": {
            "fix/mine|engine": {"branch": "fix/mine", "suite": "engine", "green": False,
                                "figures": {"passed": 500, "not_passed": 1}},
            "main|engine": {"branch": "main", "suite": "engine", "green": True,
                            "figures": {"passed": 1074}},
            "laya|feat/other|ui@two tests removed": {
                "branch": "feat/other", "suite": "ui", "green": True,
                "variant": "two tests removed", "figures": {"passed": 246}},
            "laya|feat/other|ui@file reverted": {
                "branch": "feat/other", "suite": "ui", "green": False,
                "variant": "file reverted", "figures": {"passed": 244, "not_passed": 2}},
        }}), encoding="utf-8")
        indexed, _owners, variant_index, count, _notes, _bc = load_counts(manifest)
        if count != 4:
            print(f"  FAILED: load_counts reported {count} measurements, expected 4")
            failures += 1
        if 500 in indexed.get("fix/mine", set()):
            print("  FAILED: a red run's count was indexed as a measurement")
            failures += 1
        if 246 in indexed.get("feat/other", set()):
            print("  FAILED: a counterfactual was indexed as a branch's own count")
            failures += 1
        if variant_index.get(246) != {"two tests removed"}:
            print(f"  FAILED: a counterfactual was not indexed as one ({variant_index})")
            failures += 1
        # A deliberately red mutation is evidence, not a branch measurement — but its
        # redness has to travel with it or the note reads as if the tip were red.
        red = " ".join(variant_index.get(244, ()))
        if "red on purpose" not in red or "2 not passing" not in red:
            print(f"  FAILED: a red counterfactual lost its redness ({variant_index})")
            failures += 1
        if indexed.get("main") != {1074}:
            print(f"  FAILED: green counts were not indexed ({indexed})")
            failures += 1
    return failures


def _self_test_routes() -> int:
    """Prove route claims are checked, using the two mistakes this caught.

    Both were real, in the first draft of the cross-site PR: a route named
    `POST /settings/prompts/reload` that does not exist (it is `POST /prompts/reload`),
    and `PUT /sources/workflows/{id}/active` offered as reachable from a cross-site
    page when it takes a JSON body.
    """
    print("self-test: route claims, including a body-taking route offered as reachable")
    failures = 0
    sources = {
        "engine/laya/main.py": (
            "from laya.api.sources_api import router as sources_router\n"
            "app.include_router(sources_router)\n"
            '@app.post("/prompts/reload")\nasync def reload_prompts() -> dict:\n'),
        "engine/laya/api/cards_api.py": (
            '@router.post("/cards/read-all")\nasync def mark_all_read(date: str | None = None):\n'),
        "engine/laya/api/sources_api.py": (
            "class ActiveRequest(BaseModel):\n    active: bool\n\n"
            '@router.put("/sources/workflows/{workflow_id}/active")\n'
            "async def set_active(workflow_id: str, body: ActiveRequest):\n"),
    }
    routes = declared_routes(sources)
    cases = [
        (("POST", "/prompts/reload"), False, "a declared, body-less route"),
        (("POST", "/cards/read-all"), False, "a body-less route in an api module"),
        (("PUT", "/sources/workflows/{}/active"), True, "a route whose handler takes a BaseModel"),
    ]
    for key, expected_body, description in cases:
        if key not in routes:
            print(f"  FAILED: {description} was not extracted ({key})")
            failures += 1
        elif routes[key] != expected_body:
            print(f"  FAILED: {description}: takes_body={routes[key]}, expected {expected_body}")
            failures += 1

    files = ["engine/laya/main.py"]
    tree = sources["engine/laya/main.py"]

    bad_fails, _, _ = check_body_text(
        "A page could `POST /settings/prompts/reload`.\n", files, tree, set(),
        routes=routes)
    if not any("not declared" in f for f in bad_fails):
        print(f"  FAILED: an undeclared route was not reported ({bad_fails})")
        failures += 1

    body_fails, body_notes, _ = check_body_text(
        "A page could `PUT /sources/workflows/{id}/active`.\n", files, tree, set(),
        routes=routes)
    if body_fails:
        print(f"  FAILED: a declared route was reported missing ({body_fails})")
        failures += 1
    if not any("takes a request body" in n for n in body_notes):
        print(f"  FAILED: a body-taking route was not flagged as unreachable ({body_notes})")
        failures += 1

    if not failures:
        print("  ok: an undeclared route fails, and a body-taking route is called out")
    return failures


if __name__ == "__main__":
    sys.exit(main())
