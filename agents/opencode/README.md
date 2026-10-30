# opencode agent definitions

Every agent this project uses, kept here because the live copies live in
`~/.config/opencode/agent/` — outside the repo, and therefore the first thing a
rebuild or a fresh checkout loses.

68 definitions. They are opencode agent files (YAML front matter + body), not
skills: an agent is a *role* the orchestrator can dispatch, a skill is *knowledge*
it loads. The two work together — see `../hunt_prompt.md` for the round prompt and
`../../skills/local/` for the project-authored skills.

## The ones that matter for bug bounty

| agent | role |
|---|---|
| `bughunter-autopilot.md` | Primary orchestrator. 5-phase recon, dispatch a specialist per vuln class, chain findings, adversarially validate, write reports. It also carries the tool-path reality (`export PATH=…`, which binaries are installed, which are installed but off-PATH, and which are present-but-unusable) — that list was checked on this machine and should be re-checked rather than trusted. |
| `web-vuln-hunter.md`, `{xss,sqli,ssrf,idor,rce,ssti,xxe,csrf,cors,oauth,graphql,mobile,cloud,llm-ai,forensics,reverse}-hunter.md` | The per-class specialists the orchestrator fans out to. |
| `recon.md`, `recon-deep.md`, `recon-ranker.md`, `js-analyzer.md`, `secrets-hunter.md`, `subdomain-takeover.md`, `waf-profiler.md`, `tls-dns-hunter.md` | Recon and surface ranking. |
| `sast-*.md` (7) | The source-code review track: entry-point mapping, dangerous-op mapping, flow tracing, gap analysis, file ranking, exploit building, and a devil's advocate on every SAST finding. |
| `portswigger-lab-solver.md`, `training-apps-hunter.md` | Deliberately-vulnerable training targets (Academy, DVWA, bWAPP, Juice Shop, crAPI, DVGA) — where the skills in this repo were verified. |
| `chain-builder.md`, `correlator.md`, `dast-devils-advocate.md`, `validator.md`, `triage-reporter.md`, `poc-builder.md`, `report-writer.md`, `quality-check.md` | Post-hunt: chaining individual findings into real impact, falsifying them, and reporting. |
| `scope-check.md`, `brain.md`, `monitor.md`, `cost.md` | Guardrails: scope enforcement, engagement memory, change monitoring, budget. |

## Installing

```sh
bash scripts/install-agent-assets.sh          # skills + agents
bash scripts/install-agent-assets.sh agents   # agents only
```

The script copies (does not symlink) into `~/.config/opencode/agent/`, so an
upstream refresh of an agent does not silently change what the repo ships. Edit
here, install, then run the pipeline.

## Note on `hunt_prompt.md`

`../hunt_prompt.md` is the *pipeline's* prompt — the template `hunt.py` renders per
round. It is not an opencode agent definition and is deliberately kept one level
up: the agent definitions are roles a human or the autopilot picks, while the hunt
prompt is generated, populated with recon data, and never hand-edited.
