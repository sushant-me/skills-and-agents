---
name: sploit-agent-catalog
description: Advanced external-attack technique catalog (SploitAgent) covering web, API, cloud, recon, code-review, AI/ML, mobile, and payloads. Use when a hunt-* skill needs a deeper or less-common technique, bypass, or payload.
source_repo: custom
source_path: ''
source_license: original
---
# SploitAgent Technique Catalog

A curated catalog of advanced, external-facing attack techniques lives at:

`/home/logic/ghar ko sathi/_work/repos/SploitAgent/`

Consult these when a standard `hunt-*` skill is not enough:

- `CATALOG.md` — master index of techniques by category
- `methodology.md` — full kill-chain methodology
- `skills/web/`, `skills/api/`, `skills/cloud/`, `skills/recon/` — per-category README technique guides
- `skills/payloads/`, `skills/code-review/`, `skills/ai-ml/`, `skills/mobile/` — payloads, SAST, AI/ML, mobile attack surface
- `skills/_templates/arsenal.md` + `technique.md` — per-finding arsenal/technique format

Usage: read the relevant `skills/<category>/README.md` for a target's tech stack, then apply the technique with the concrete payloads/commands from `CATALOG.md`.

External-only: this catalog covers the internet-reachable surface (web/API/cloud/mobile). Internal AD / C2 / post-exploit entries are irrelevant for bug bounty and must not be used.
