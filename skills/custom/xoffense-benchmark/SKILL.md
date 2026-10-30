---
name: xoffense-benchmark
description: Methodology for offensive-security agent benchmarks (XOffense-style) — structured multi-step exploitation tasks with success criteria. Use when evaluating an agent on an offense benchmark or CTF-style scored challenges.
source_repo: custom
source_path: ''
source_license: original
---
# XOffense-style Offense Benchmark

Agent-offense benchmarks score an agent on completing structured exploitation
tasks (often CTF-derived) with a verifiable success condition (a flag, a file, a
state change). Approach:

1. **Parse the task** — identify the target (host:port, files provided), the
   objective (flag format / goal), and constraints.
2. **Recon** — fingerprint the service; enumerate ports, endpoints, versions.
3. **Identify the class** — web/API, pwn, crypto, reverse, forensics, blockchain.
   Load the matching skill.
4. **Exploit step-by-step** — build the exploit, verify each step, adapt on failure.
5. **Prove success** — capture the exact evidence the grader checks (flag/answer).
6. **Report** — write the steps + PoC so it's reproducible.

Treat each task as an in-scope authorized challenge. Capture the winning request
and the success proof.
