#!/usr/bin/env python3
"""Rebuild MANIFEST.json from the archive on disk.

The manifest is the machine-readable inventory of the archive: every skill with
its path and SHA-256, every agent preset, the ten vendored collections, the
catalog-name aliases and the three documented upstream name collisions.

Run from anywhere:  python3 tools/build_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, "skills")
AGENTS = os.path.join(REPO, "agents")
MANIFEST = os.path.join(REPO, "MANIFEST.json")

# Installed-catalog names whose skill is stored in the archive under the
# upstream directory name (the catalog installer renames a handful of skills).
ALIASES = {
    "bountyforge": "skills/Gabson0x_bountyforge/SKILL.md",
    "bug-reaper": "skills/shaniidev_bug-reaper/SKILL.md",
    "cmk-exploit-file-download": "skills/crazyMarky_pentest-skills/exploit-file-download/scripts/SKILL.md",
    "techstack-backend": "skills/transilienceai_communitytools/skills/techstack-identification/backend/SKILL.md",
    "techstack-correlation": "skills/transilienceai_communitytools/skills/techstack-identification/correlation/SKILL.md",
    "techstack-frontend": "skills/transilienceai_communitytools/skills/techstack-identification/frontend/SKILL.md",
    "techstack-infra": "skills/transilienceai_communitytools/skills/techstack-identification/infra/SKILL.md",
    "techstack-osint": "skills/transilienceai_communitytools/skills/techstack-identification/osint/SKILL.md",
    "techstack-security": "skills/transilienceai_communitytools/skills/techstack-identification/security/SKILL.md",
    "trc-transilience-report-style": "skills/transilienceai_communitytools/formats/transilience-report-style/SKILL.md",
}

# Same directory name, different skill content, inherited from upstream layout.
NAME_COLLISIONS = {
    "offensive-osint": [
        "skills/SnailSploit_Claude-Red/Skills/recon/offensive-osint/SKILL.md",
        "skills/elementalsouls_Claude-BugHunter/skills/offensive-osint/SKILL.md",
    ],
    "osint": [
        "skills/transilienceai_communitytools/skills/osint/SKILL.md",
        "skills/transilienceai_communitytools/skills/techstack-identification/osint/SKILL.md",
    ],
    "transilience-report-style": [
        "skills/transilienceai_communitytools/formats/transilience-report-style/SKILL.md",
        "skills/transilienceai_communitytools/skills/transilience-report-style/SKILL.md",
    ],
}

SOURCES = {
    "mukul975_Anthropic-Cybersecurity-Skills": (
        "https://github.com/mukul975/Anthropic-Cybersecurity-Skills", "Apache-2.0"),
    "trailofbits_skills": ("https://github.com/trailofbits/skills", "CC-BY-SA-4.0"),
    "SnailSploit_Claude-Red": ("https://github.com/SnailSploit/Claude-Red", "MIT"),
    "elementalsouls_Claude-BugHunter": (
        "https://github.com/elementalsouls/Claude-BugHunter", "MIT"),
    "transilienceai_communitytools": (
        "https://github.com/transilienceai/communitytools", "MIT"),
    "crazyMarky_pentest-skills": (
        "https://github.com/crazyMarky/pentest-skills", "Apache-2.0"),
    "x-glacier_kali-pentest": ("https://github.com/x-glacier/kali-pentest", "Apache-2.0"),
    "Eyadkelleh_awesome-skills-security": (
        "https://github.com/Eyadkelleh/awesome-skills-security", "NO LICENCE DECLARED"),
    "Gabson0x_bountyforge": (
        "https://github.com/Gabson0x/bountyforge", "NO LICENCE DECLARED"),
    "shaniidev_bug-reaper": ("https://github.com/shaniidev/bug-reaper", "MIT"),
    "cloudflare_security-audit-skill": ("cloudflare/security-audit-skill", "see upstream"),
    "custom": ("written for this project", "original"),
    "unattributed": ("installed without provenance metadata", "unknown"),
    "local-authored": ("written locally (CTF / platform / tooling work)", "original"),
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def skill_entries() -> list[dict]:
    entries = []
    for root, category_root in (("skills", SKILLS), ("agents", AGENTS)):
        for dirpath, dirnames, filenames in os.walk(category_root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            if "SKILL.md" not in filenames:
                continue
            rel = os.path.relpath(os.path.join(dirpath, "SKILL.md"), REPO)
            if root == "skills":
                category = os.path.relpath(dirpath, SKILLS).split(os.sep)[0]
            else:
                category = "agents/" + os.path.basename(dirpath)
            entries.append({
                "name": os.path.basename(dirpath),
                "category": category,
                "path": rel,
                "sha256": sha256_file(os.path.join(REPO, rel)),
            })
    entries.sort(key=lambda e: e["path"])
    return entries


def preset_entries() -> list[dict]:
    presets = []
    for name in sorted(os.listdir(AGENTS)):
        pdir = os.path.join(AGENTS, name)
        if not os.path.isfile(os.path.join(pdir, "preset.yml")):
            continue
        files = []
        for dirpath, dirnames, filenames in os.walk(pdir):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for f in filenames:
                if f.endswith((".pyc", ".bak")) or f.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, f), REPO)
                files.append({"path": rel, "sha256": sha256_file(os.path.join(REPO, rel))})
        presets.append({"name": name, "path": os.path.relpath(pdir, REPO), "files": files})
    return presets


def agent_definitions() -> list[dict]:
    """Claude Code (opencodex-generated) and opencode agent definition files."""
    out = []
    for group in ("opencodex", "opencode"):
        adir = os.path.join(AGENTS, group)
        if not os.path.isdir(adir):
            continue
        for f in sorted(os.listdir(adir)):
            if not f.endswith(".md") or f == "README.md":
                continue
            out.append({"group": group,
                        "path": os.path.relpath(os.path.join(adir, f), REPO),
                        "sha256": sha256_file(os.path.join(adir, f))})
    return out


def agent_prompts() -> list[dict]:
    out = []
    p = os.path.join(AGENTS, "hunt_prompt.md")
    if os.path.isfile(p):
        out.append({"path": os.path.relpath(p, REPO), "sha256": sha256_file(p)})
    return out


def collections(skills: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for s in skills:
        if s["category"] != "agents" and not s["category"].startswith("agents/"):
            counts[s["category"]] = counts.get(s["category"], 0) + 1
    out = []
    for name in sorted(counts):
        upstream, license_ = SOURCES.get(name, ("unknown", "unknown"))
        out.append({"dir": name, "upstream": upstream, "license": license_,
                    "skills": counts[name]})
    return out


def main() -> int:
    skills = skill_entries()
    presets = preset_entries()
    defs = agent_definitions()
    prompts = agent_prompts()
    names = [s["name"] for s in skills]
    collisions = {
        n: sorted(p for p in (s["path"] for s in skills) if os.path.basename(os.path.dirname(p)) == n)
        for n in NAME_COLLISIONS
    }
    manifest = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "skill_dirs": len(skills),
            "skill_names_unique": len(set(names)),
            "vendored_skills": sum(1 for s in skills if not s["category"].startswith(
                ("custom", "unattributed", "local-authored", "cloudflare", "agents"))),
            "presets": len(presets),
            "agent_definitions": len(defs),
            "agent_prompts": len(prompts),
            "collections": len(collections(skills)),
        },
        "collections": collections(skills),
        "skills": skills,
        "presets": presets,
        "agent_definitions": defs,
        "agent_prompts": prompts,
        "aliases": ALIASES,
        "name_collisions": collisions,
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print(f"wrote {MANIFEST}: {len(skills)} skill dirs, {len(presets)} presets, "
          f"{len(defs)} agent definitions, {len(prompts)} prompt(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
