# skills-and-agents

A private archive of the agent skills and agent presets used on this machine,
vendored so they survive upstream deletions, branch churn and re-clones.

**1,069 skills** — 1,055 across 9 vendored upstream collections, plus 14 CTF
skills inside the `ctf-operator` agent preset. 8,267 tracked files, ~69 MB
packed.

## Layout

```
skills/
  <upstream-repo>/        vendored verbatim, upstream LICENSE kept inside
agents/
  ctf-operator/           agent preset (preset.yml, agent.cordis.yml, tools, skills)
SOURCES.md                upstream URL, licence and skill count per directory
```

## Using a skill

Each skill is a directory containing a `SKILL.md` with YAML front matter
(`name`, `description`). Point your agent framework's skill root at
`skills/<upstream>/.../` — the directory layout inside each upstream is
preserved, so upstream documentation about where skills live still applies.

To list them:

```
find skills -name SKILL.md | wc -l
find skills -name SKILL.md | head
```

## Licence position

This repository is a **collection**, not a single work. Each vendored directory
keeps its own licence and notice — see [SOURCES.md](SOURCES.md).

Two of the nine upstream collections declare no licence at all. They are here
because this repository is private and treated as an archive; they should be
removed before this is ever made public. The exact commands are in SOURCES.md.

`trailofbits_skills` is CC BY-SA 4.0 (share-alike) and must stay unmodified
unless the modified copy also carries that licence.

Nothing in this repository is mine to relicense except `agents/ctf-operator/`.
