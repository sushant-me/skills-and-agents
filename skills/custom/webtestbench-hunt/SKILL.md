---
name: webtestbench-hunt
description: Methodology for WebTestBench-style web-agent benchmarks — completing realistic web tasks in a browser (navigation, forms, multi-step flows, data extraction) and evaluating computer-use agents on websites. Use for browser-driven web task benchmarks or any SPA flow the agent must complete in a real browser.
source_repo: custom
source_path: ''
source_license: original
---
# WebTestBench-style Web Agent Benchmark

These benchmarks evaluate an agent completing realistic **web tasks in a real
browser** (React/Vue/Angular SPAs): navigation, authentication, forms, multi-step
workflows, and data extraction.

## Approach
1. **Open the site in a real browser** (Playwright/Chromium headless) — do NOT
   rely on static HTML crawlers for SPAs.
2. **Observe** — read the rendered DOM + network calls (XHR/fetch) to find the real
   backend API the SPA uses.
3. **Act** — click, fill forms, handle auth (login/OTP), navigate multi-step flows.
4. **Extract** — pull the required data / reach the goal state.
5. **Verify** — confirm the goal (specific text, state, or data).

For security testing of such apps, test the discovered API endpoints for IDOR/authz
(see `hunt-spa-api`, `sa-api-bola`). Report any vulnerability with the request +
response and a screenshot of the rendered proof.
