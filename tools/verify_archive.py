#!/usr/bin/env python3
"""Verify that this archive is complete, deduplicated and internally consistent.

Checks, in order:

  1. MANIFEST.json matches the files on disk (every skill path + SHA-256).
  2. No two skills in the archive have identical bodies (duplicates).
  3. The only duplicate skill *names* are the documented upstream collisions.
  4. Every skill installed in the live catalog (~/.agents/skills) is represented
     in the archive, either by name or through a recorded upstream alias.
  5. Every live agent preset (~/.dsh/.agent-presets/*) is archived file-for-file.
  6. Every live Claude Code subagent definition (~/.claude/agents/*.md) is
     archived byte-for-byte.

Checks 4-6 are skipped with a warning when the live paths are absent (for
example on a fresh clone on another machine); checks 1-3 always run.

Usage:
    python3 tools/verify_archive.py [--catalog DIR] [--presets DIR] [--claude-agents DIR]
Exit code 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "MANIFEST.json")
SKILLS = os.path.join(REPO, "skills")
AGENTS = os.path.join(REPO, "agents")

DEFAULT_CATALOG = os.path.expanduser("~/.agents/skills")
DEFAULT_PRESETS = os.path.expanduser("~/.dsh/.agent-presets")
DEFAULT_CLAUDE_AGENTS = os.path.expanduser("~/.claude/agents")

JUNK = ("__pycache__", ".git", ".pytest_cache")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def body_hash(path: str) -> str:
    """Hash a SKILL.md without its YAML front matter (provenance wrapper)."""
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.match(r"^---\r?\n.*?\r?\n---\r?\n?", text, re.S)
    if m:
        text = text[m.end():]
    return hashlib.sha256(text.strip().encode()).hexdigest()


def walk_skill_files(root: str) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in JUNK]
        if "SKILL.md" in filenames:
            out.append(os.path.join(dirpath, "SKILL.md"))
    return out


def walk_catalog_skills(root: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name, "SKILL.md")
        if os.path.isfile(p):
            out[name] = p
    return out


def files_under(root: str) -> dict[str, str]:
    """relative path -> absolute path, skipping junk and dot/backup files."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in JUNK]
        for f in filenames:
            if f.endswith(".pyc") or ".bak" in f or f.startswith("."):
                continue
            p = os.path.join(dirpath, f)
            out[os.path.relpath(p, root)] = p
    return out


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)


def check_manifest(rep: Report) -> dict:
    if not os.path.isfile(MANIFEST):
        rep.fail("MANIFEST.json missing - run tools/build_manifest.py")
        return {}
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    expected = {s["path"]: s["sha256"] for s in manifest.get("skills", [])}
    actual_paths = walk_skill_files(SKILLS) + walk_skill_files(AGENTS)
    actual = {os.path.relpath(p, REPO): sha256_file(p) for p in actual_paths}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(p for p in set(expected) & set(actual) if expected[p] != actual[p])
    if missing:
        rep.fail(f"manifest lists {len(missing)} skill(s) not on disk: {missing[:5]}")
    if extra:
        rep.fail(f"{len(extra)} skill(s) on disk are absent from the manifest: {extra[:5]}")
    if changed:
        rep.fail(f"{len(changed)} skill file(s) changed since the manifest: {changed[:5]}")
    if not (missing or extra or changed):
        rep.info(f"manifest matches disk: {len(actual)} skill files, all SHA-256 identical")
    return manifest


def check_duplicates(rep: Report, manifest: dict) -> None:
    paths = walk_skill_files(SKILLS) + walk_skill_files(AGENTS)
    by_body: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for p in paths:
        by_body.setdefault(body_hash(p), []).append(os.path.relpath(p, REPO))
        by_name.setdefault(os.path.basename(os.path.dirname(p)), []).append(
            os.path.relpath(p, REPO))
    body_dups = {h: v for h, v in by_body.items() if len(v) > 1}
    if body_dups:
        for v in body_dups.values():
            rep.fail(f"duplicate skill content: {v}")
    else:
        rep.info(f"no duplicate skill bodies among {len(paths)} skill files")

    allowed = {name: sorted(paths_) for name, paths_ in
               (manifest.get("name_collisions") or {}).items()}
    actual_collisions = {n: sorted(v) for n, v in by_name.items() if len(v) > 1}
    unexpected = {n: v for n, v in actual_collisions.items() if allowed.get(n) != v}
    missing_collisions = {n: v for n, v in allowed.items() if actual_collisions.get(n) != v}
    if unexpected:
        rep.fail(f"undocumented duplicate skill name(s): {unexpected}")
    if missing_collisions:
        rep.fail(f"documented name collision(s) changed: {missing_collisions}")
    if not (unexpected or missing_collisions):
        rep.info(f"only the {len(allowed)} documented upstream name collision(s) exist")


def check_catalog(rep: Report, catalog: str, manifest: dict) -> None:
    live = walk_catalog_skills(catalog)
    if not live:
        rep.warn(f"live catalog absent ({catalog}) - completeness check skipped")
        return
    repo_names = {os.path.basename(os.path.dirname(p))
                  for p in walk_skill_files(SKILLS) + walk_skill_files(AGENTS)}
    aliases = manifest.get("aliases") or {}
    missing = sorted(n for n in live if n not in repo_names and n not in aliases)
    if missing:
        rep.fail(f"{len(missing)} installed skill(s) not in archive: {missing[:8]}")
    else:
        rep.info(f"all {len(live)} installed skills represented "
                 f"({len(aliases)} via upstream aliases)")
    bad_alias = []
    for name, rel in aliases.items():
        p = os.path.join(REPO, rel)
        if not os.path.isfile(p):
            bad_alias.append(name)
        elif name in live and body_hash(p) != body_hash(live[name]):
            bad_alias.append(name)
    if bad_alias:
        rep.fail(f"alias target missing or body differs: {bad_alias}")
    repo_bodies: dict[str, set[str]] = {}
    for p in walk_skill_files(SKILLS) + walk_skill_files(AGENTS):
        repo_bodies.setdefault(os.path.basename(os.path.dirname(p)), set()).add(body_hash(p))
    drift = sorted(n for n in set(live) & repo_names
                   if body_hash(live[n]) not in repo_bodies.get(n, set()))
    if drift:
        rep.warn(f"{len(drift)} skill body differs from the installed catalog "
                 f"(archive holds a newer upstream revision): {drift}")


def check_presets(rep: Report, presets: str, manifest: dict) -> None:
    if not os.path.isdir(presets):
        rep.warn(f"live presets absent ({presets}) - preset check skipped")
        return
    archived = {p["name"]: p for p in manifest.get("presets", [])}
    live = [d for d in sorted(os.listdir(presets))
            if os.path.isfile(os.path.join(presets, d, "preset.yml"))]
    missing = [d for d in live if d not in archived]
    if missing:
        rep.fail(f"agent preset(s) not archived: {missing}")
    for name in live:
        if name not in archived:
            continue
        preset_dir = os.path.join(presets, name)
        live_files = files_under(preset_dir)
        arch_dir = os.path.join(AGENTS, name)
        arch = {os.path.relpath(os.path.join(REPO, f["path"]), arch_dir): f["sha256"]
                for f in archived[name]["files"]}
        for rel, p in live_files.items():
            if rel not in arch:
                rep.fail(f"preset {name}: live file not archived: {rel}")
            elif arch[rel] != sha256_file(p):
                rep.fail(f"preset {name}: archived copy differs: {rel}")
    if not missing:
        rep.info(f"all {len(live)} agent preset(s) archived file-for-file")


def check_agent_definitions(rep: Report, claude_agents: str, manifest: dict) -> None:
    if not os.path.isdir(claude_agents):
        rep.warn(f"live Claude agents absent ({claude_agents}) - check skipped")
        return
    arch = {os.path.basename(d["path"]): d["sha256"]
            for d in manifest.get("agent_definitions", [])}
    live = [f for f in sorted(os.listdir(claude_agents)) if f.endswith(".md")]
    missing = [f for f in live if f not in arch]
    if missing:
        rep.fail(f"Claude subagent definition(s) not archived: {missing}")
    changed = [f for f in live if f in arch
               and arch[f] != sha256_file(os.path.join(claude_agents, f))]
    if changed:
        rep.fail(f"archived subagent definition differs: {changed}")
    if not missing and not changed:
        rep.info(f"all {len(live)} Claude subagent definition(s) archived byte-for-byte")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", default=DEFAULT_CATALOG)
    ap.add_argument("--presets", default=DEFAULT_PRESETS)
    ap.add_argument("--claude-agents", default=DEFAULT_CLAUDE_AGENTS)
    args = ap.parse_args()

    rep = Report()
    manifest = check_manifest(rep)
    if manifest:
        check_duplicates(rep, manifest)
        check_catalog(rep, args.catalog, manifest)
        check_presets(rep, args.presets, manifest)
        check_agent_definitions(rep, args.claude_agents, manifest)

    print(f"archive: {REPO}")
    if manifest:
        c = manifest.get("counts", {})
        print(f"  skills: {c.get('skill_dirs')} dirs / {c.get('skill_names_unique')} names / "
              f"{c.get('vendored_skills')} vendored | presets: {c.get('presets')} | "
              f"agent definitions: {c.get('agent_definitions')}")
    for line in rep.infos:
        print(f"  OK   {line}")
    for line in rep.warnings:
        print(f"  WARN {line}")
    for line in rep.failures:
        print(f"  FAIL {line}")
    print()
    if rep.failures:
        print(f"FAIL: {len(rep.failures)} check(s) failed")
        return 1
    print(f"PASS: {len(rep.infos)} checks passed, {len(rep.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
