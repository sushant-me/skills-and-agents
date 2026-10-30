# Installed-catalog provenance (snapshot)

`catalog-manifest-2026-09-10.json` is the manifest that the skill installer wrote
for the live catalog at `~/.agents/skills` on 2026-09-10 (1,291 skills: 1,013
vendored, 278 custom). It maps every installed skill name to its upstream
collection, upstream path, licence and SHA-256 hashes.

It is kept here as provenance, not as a second copy of the catalog: the archive
stores each skill once, at its upstream path. Skills installed later than the
snapshot (the HackSkills-style set and the Claude-BugHunter collection) are
described in [../SOURCES.md](../SOURCES.md).

Do not treat the hashes as an integrity gate for the archive: several vendored
collections have moved on since the snapshot, and this archive stores the newer
upstream revision.
