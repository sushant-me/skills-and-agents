#!/usr/bin/env python3
"""Disable one guard at a time in a preset tool and ask: does its own self-test notice?

The gap this exists for was found by accident in round 63: a mutant that replaced
`for path in parse_binary_files(numstat)` with an empty list passed
`audit_prepared_work.py --self-test`, because the self-test exercised the *parsers* and
nothing exercised the call site. A self-test that does not fail when its guard is disabled
is not evidence about that guard.

Usage:  python3 mutation_sweep.py [tool.py ...]
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent

# (tool, label, exact source text to replace, replacement)
#
# Two kinds of mutation do not belong here, and both were removed after they reported as
# blind spots that no test could ever close:
#
#   * one INSIDE a `self_test` body — disabling an assertion cannot be caught by that
#     assertion, so it measures nothing (check_laya_home's verdict comparison);
#   * an EQUIVALENT mutant, where a second guard already produces the same result for the
#     same input — `handoff_status`'s upstream-existence check returns None, and the very
#     next guard returns None too because the count comes back non-numeric, so no
#     observable behaviour differs and no test can tell them apart.
#
# Every anchor here must be in PRODUCTION code. A mutation inside the tool's own
# `self_test` disables the very assertion that would report it, so it measures nothing —
# two of those (check_laya_home's verdict comparison, handoff_status's unpushed check)
# were in the first version of this list and were removed for that reason.
MUTATIONS: list[tuple[str, str, str, str]] = [
    # ── submit_prepared_work: the guards that stop a bad push ──────────────
    ("submit_prepared_work.py", "conflict refusal",
     "    conflict = merge_conflict(clone, branch)\n    if conflict:",
     "    conflict = merge_conflict(clone, branch)\n    if False:"),
    ("submit_prepared_work.py", "dirty-tree refusal",
     "    dirty = run([\"git\", \"-C\", str(clone), \"status\", \"--porcelain\"], check=False)\n    if dirty:",
     "    dirty = run([\"git\", \"-C\", str(clone), \"status\", \"--porcelain\"], check=False)\n    if False:"),
    ("submit_prepared_work.py", "missing-body refusal",
     "    if not body.is_file():\n        raise Stop(f\"PR text {body} is missing\")",
     "    if False:\n        raise Stop(f\"PR text {body} is missing\")"),
    ("submit_prepared_work.py", "empty-branch refusal",
     "    reason = empty_branch_reason(ahead, branch)\n    if reason:",
     "    reason = empty_branch_reason(ahead, branch)\n    if False:"),
    ("submit_prepared_work.py", "conflict detection body",
     "    hits = [ln.strip() for ln in out.splitlines() if \"CONFLICT\" in ln.upper()]",
     "    hits = []"),
    ("submit_prepared_work.py", "branch-exists refusal",
     "    if run([\"git\", \"-C\", str(clone), \"rev-parse\", \"--verify\", \"--quiet\", branch],\n           check=False) == \"\":",
     "    if False:"),
    ("submit_prepared_work.py", "title extraction",
     "    raise Stop(f\"{body.name} has no '# Title' heading to use as the PR title\")",
     "    return \"\"  # mutated: no title"),

    # ── check_pr_bodies: the claim checks ──────────────────────────────────
    ("check_pr_bodies.py", "path claim",
     "        failures.append(f\"path `{token}` is not in the branch\")",
     "        pass  # mutated"),
    ("check_pr_bodies.py", "route claim",
     "            failures.append(f\"route `{raw.strip()}` is not declared by this branch\")",
     "            pass  # mutated"),
    ("check_pr_bodies.py", "count cross-check",
     "        failures.append(f\"count `{figure} passed` is not this branch's measured count; \"",
     "        pass  # mutated: the misattributed-count failure is never raised"),
    ("check_pr_bodies.py", "title markdown",
     "                failures.append(f\"{branch}: the title contains `{marker}`, which is {what} \"",
     "                pass or failures.append(f\"{branch}: the title contains `{marker}`, which is {what} \""),
    ("check_pr_bodies.py", "requires the manifest",
     "    if measurements or not required:\n        return None",
     "    return None"),

    # ── measure_prepared_counts: refusing to invent a figure ───────────────
    ("measure_prepared_counts.py", "refuses a figureless run",
     "        if figures is None:",
     "        if False:"),
    ("measure_prepared_counts.py", "green flag",
     "            record[\"green\"] = proc.returncode == 0 and \"not_passed\" not in figures",
     "            record[\"green\"] = True"),
    ("measure_prepared_counts.py", "pre-suite failure",
     "            if prep.returncode != 0:",
     "            if False:"),

    # ── audit_prepared_work: the index and branch checks ───────────────────
    ("audit_prepared_work.py", "branch-count mismatch",
     "        elif number != size:",
     "        elif False:"),
    ("audit_prepared_work.py", "runbook coverage",
     "        if seen == 0:",
     "        if False:"),
    ("audit_prepared_work.py", "test removal",
     "        if after_count < before_count:",
     "        if False:"),
    ("audit_prepared_work.py", "push-count total",
     "        if int(match.group(1)) != total:",
     "        if False:"),
    ("audit_prepared_work.py", "hazard: whitespace is not a failure",
     '        if "conflict" in line.lower():',
     '        if True:'),
    ("audit_prepared_work.py", "binary file call site",
     "    for path in parse_binary_files(numstat):",
     "    for path in []:"),
    ("audit_prepared_work.py", "mode change call site",
     "    for old, new, path in parse_mode_changes(raw):",
     "    for old, new, path in []:"),

    # ── verify_everything: the classification and the record ───────────────
    ("verify_everything.py", "a failing check is a FAIL",
     '        status = "PASS" if code == 0 else "FAIL"',
     '        status = "PASS"'),
    ("verify_everything.py", "FLAKY detection",
     "        if code != 0 and check.retry:",
     "        if False:"),
    ("verify_everything.py", "failure is named",
     '        named = [l.strip() for l in output if l.strip().startswith("FAILED")]',
     "        named = []"),
    ("verify_everything.py", "run is recorded",
     "        RUN_LOG.mkdir(parents=True, exist_ok=True)",
     "        return None"),
    ("verify_everything.py", "history surfaces failures",
     '        failed = [r for r in record["results"] if r["status"] != "PASS"]',
     "        failed = []"),

    # ── check_laya_home: every verdict reachable ──────────────────────────
    ("check_laya_home.py", "scratch marker honoured",
     '        os.environ.pop("LAYA_HOME_IS_SCRATCH", None)',
     '        os.environ["LAYA_HOME_IS_SCRATCH"] = "1"'),


    # ── handoff_status: unpushed detection ────────────────────────────────

    # ── verify_claims: a path claim that does not exist goes red ──────────
    ("verify_claims.py", "missing path is FAIL",
     '            rep.add(f"path {rel}", FAIL, "named in the skill but does not exist")',
     '            rep.add(f"path {rel}", PASS, "mutated")'),

    ("compose_prepared_branches.py", "the record carries the figures",
     '            record["checks"].append({"label": label, "status": status, "detail": detail,',
     '            record["checks"].append({"label": label, "status": "PASS", "detail": detail,'),

    ("audit_prepared_work.py", "the index count check",
     '    for branch, claimed in index_branch_claims(text):',
     "    for branch, claimed in []:"),
    ("audit_prepared_work.py", "the composed-record comparison",
     '                elif got != want:',
     "                elif False:"),

    ("measure_prepared_counts.py", "legacy keys are migrated",
     "    migrate_legacy_keys(data, path)",
     "    pass"),
    ("check_pr_bodies.py", "the manifest is migrated before reading",
     "        notes = module.migrate_legacy_keys(data, path)",
     "        notes = []"),

    # -- handoff_status: what the user is told is still outstanding --------
    ("handoff_status.py", "a level branch is not unpushed",
     '    if not count or count == "0":',
     "    if False:"),
    # -- compose_prepared_branches: the headline green --------------------
    ("compose_prepared_branches.py", "a failing suite reddens the verdict",
     '            ok = ok and status == "PASS"',
     "            ok = ok"),
    ("compose_prepared_branches.py", "a conflict reddens the verdict",
     '                return False, lines + [f"    CONFLICT merging {branch}: {exc}"]',
     "                return True, lines"),
    ("compose_prepared_branches.py", "main can print FAILURES",
     '    print("COMPOSED SET IS GREEN" if all_ok else "COMPOSED SET HAS FAILURES")',
     '    print("COMPOSED SET IS GREEN")'),
    ("compose_prepared_branches.py", "main can exit non-zero",
     "    return 0 if all_ok else 1",
     "    return 0"),
    ("compose_prepared_branches.py", "dirty tree refused",
     "    if dirty:",
     "    if False:"),
    ("compose_prepared_branches.py", "result line preferred over the last line",
     "        detail = (result[-1] if result else",
     '        detail = (next((l.strip() for l in reversed(output) if l.strip()), "")'
     " if result else"),
]

# Behaviour-preserving changes the self-test is EXPECTED to miss. Without one of these,
# a sweep that reported "everything caught" would be indistinguishable from a sweep that
# reports every mutant as caught for the wrong reason — an ImportError, a syntax error from
# a bad substitution, a tool that refuses to start. If a control comes back caught, the
# harness is lying and this exits non-zero.
CONTROLS: list[tuple[str, str, str, str]] = [
    ("submit_prepared_work.py", "control — a wider conflict slice changes nothing the "
                                "self-test asserts",
     r'    return "\n".join(hits[:3]) if hits else None',
     r'    return "\n".join(hits[:4]) if hits else None'),
]


def run_self_test(tool: pathlib.Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(tool), "--self-test"],
                          capture_output=True, text=True, timeout=900,
                          cwd=str(TOOLS))
    return proc.returncode, (proc.stdout + proc.stderr)


def main(argv: list[str]) -> int:
    wanted = set(argv) or {m[0] for m in MUTATIONS}
    blind: list[str] = []
    caught: list[str] = []
    skipped: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for tool_name, label, old, new in MUTATIONS:
            if tool_name not in wanted:
                continue
            source = (TOOLS / tool_name).read_text()
            if source.count(old) != 1:
                skipped.append(f"{tool_name}: {label} (anchor appears "
                               f"{source.count(old)}x — update the sweep)")
                continue
            # The mutant is written INTO the tools directory, not /tmp: these tools
            # resolve their siblings from `__file__`, so a /tmp copy makes
            # `plan_size()`/`plan_rows()` return empty and a self-test can then fail for
            # a reason that has nothing to do with the mutation. Writing it here keeps
            # every import exactly as it is in reality, and the finally clause removes it.
            mutant = TOOLS / f".mutant-{tool_name}"
            try:
                mutant.write_text(source.replace(old, new))
                code, out = run_self_test(mutant)
            finally:
                mutant.unlink(missing_ok=True)
            if code != 0:
                caught.append(f"{tool_name}: {label}")
            else:
                blind.append(f"{tool_name}: {label}")
    control_failures = []
    controls_ok: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for tool_name, label, old_src, new_src in CONTROLS:
            source = (TOOLS / tool_name).read_text()
            if source.count(old_src) != 1:
                control_failures.append(f"{label}: anchor appears "
                                        f"{source.count(old_src)}x")
                continue
            mutant = TOOLS / f".mutant-control-{tool_name}"
            try:
                mutant.write_text(source.replace(old_src, new_src))
                code, _out = run_self_test(mutant)
            finally:
                mutant.unlink(missing_ok=True)
            if code != 0:
                control_failures.append(f"{label}: the self-test failed, which means the "
                                        f"sweep cannot tell a caught mutant from a broken "
                                        f"one")
            else:
                controls_ok.append(f"{tool_name}: {label}")

    print(f"\ncaught by the tool's own self-test : {len(caught)}")
    for row in caught:
        print(f"   ok    {row}")
    print(f"\nbehaviour-preserving controls the self-test correctly ignored : "
          f"{len(controls_ok)}")
    for row in controls_ok:
        print(f"   ok    {row}")
    print(f"\nNOT caught (the self-test passed with the guard disabled) : {len(blind)}")
    for row in blind:
        print(f"   BLIND {row}")
    if skipped:
        print(f"\nskipped (anchor moved) : {len(skipped)}")
        for row in skipped:
            print(f"   ?     {row}")
    # A mutation whose anchor moved is coverage this sweep silently stopped providing, so
    # it is a failure rather than a footnote — the whole point is that the guard is still
    # being exercised.
    if control_failures:
        print("\nHARNESS PROBLEM — a behaviour-preserving control was reported as caught:")
        for row in control_failures:
            print(f"   !!    {row}")
    return 1 if (blind or skipped or control_failures) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
