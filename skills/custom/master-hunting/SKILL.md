---
name: master-hunting
description: Consolidated master hunting workflow — recon, surface ranking, hypothesis-driven testing per bug class, evidence-gathering, duplicate check, 7-Question Gate, report writing, and submission. Use as the single orchestrating skill for any authorized bug bounty engagement.
source_repo: custom
source_path: ''
source_license: original
---
# Master Hunting Workflow

One consolidated playbook for a full, disciplined bug-bounty engagement. Use the
specialized `hunt-*` and `sa-*` skills for in-depth technique, then return here
for the end-to-end discipline.

## 1. Scope & authorization (non-negotiable)
- Only test assets explicitly in scope. Read the program's policy first.
- Respect rate limits. No destructive tests, no mass lockout, no data deletion.
- Stop immediately if a finding is out of scope — it's not a bug, it's an incident.

## 2. Recon → surface map
- Enumerate subdomains (passive first: crt.sh, certspotter, then active).
- Fingerprint tech per host (httpx) — identify frameworks/apps that have known weaknesses.
- Crawl endpoints (JS, robots.txt, sitemap, source maps, GraphQL introspection).
- Rank the surface: prioritize API/graphql endpoints, auth flows, file upload,
  admin surfaces, and anything that processes user input server-side.

## 3. Hypothesis-driven hunting (per class)
For each likely class, form a hypothesis and test it with the concrete playbook
in the matching skill:
- IDOR/BOLA → `hunt-idor`, `sa-api-bola` (two accounts, swap IDs, diff bodies)
- XSS → `hunt-xss` (reflect/stored/DOM, filter bypass, encoding)
- SQLi → `hunt-sqli`, `hunt-nosqli` (error/time/boolean/OOB)
- SSRF → `hunt-ssrf` (internal fetch, cloud metadata, DNS rebinding)
- Auth → `hunt-oauth`, `hunt-jwt-crypto`, `sa-api-auth-attacks` (JWT alg, OAuth redirect_uri)
- Business logic / race → `hunt-business-logic`, `hunt-race-condition`
- AI/LLM features → `hunt-llm-ai`, `sa-ai-prompt-injection`
- Info disclosure / source leak → `hunt-info-disclosure`, `hunt-source-leak`

Test EVERY realistic hypothesis before concluding. Fewer, deeper, verified tests
beat many shallow ones.

## 4. Verify every finding (the bar for submission)
You may only report a bug you PROVED. For each suspected finding:
- Send the real request; capture the exact response that proves it.
- Confirm it's a real vulnerability, not the app's designed behavior.
- Confirm it's exploitable/non-trivial — not just a status code.
- Capture a screenshot of the proof (Playwright) and save it.
- Confirm the affected asset is in scope and the bug class is accepted.

## 5. Duplicate check (never re-report)
- Before reporting, search public disclosures for the program + bug class + keywords.
- Check your own prior reports.
- If a similar report is already disclosed/known, do not re-report — find a new angle.

## 6. 7-Question Gate (kill anything that fails)
1. Exact request + response proving it RIGHT NOW?
2. Bug class accepted by this program?
3. Asset in scope (owned by target, not third-party)?
4. Works without admin/privileged access?
5. Not documented behavior or a known issue?
6. Impact proved with actual data (not just a status code)?
7. Not a duplicate of a public/known report?
Any NO → discard. Do not submit.

## 7. Write the report (human tone, one shot)
- Title: `[Vuln type] in [component] allows [impact] via [vector]` (<15 words).
- First person, contractions, concrete. No AI filler, no hedging.
- Sections: Summary · Affected Asset · Type · Severity · Steps to Reproduce ·
  Proof (screenshot) · Impact · References.
- Severity: honest (RCE/SQLi=critical; IDOR/XSS=high; CSRF/CORS=medium; redirect=low).

## 8. Submit
- Move to approved, submit via the approved channel with the screenshot attached.
- Log the report ID. Update your record.
- Only after the go-ahead. Never junk-submit — that destroys Signal and reputation.
