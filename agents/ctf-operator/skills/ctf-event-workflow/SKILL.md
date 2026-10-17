---
name: ctf-event-workflow
description: Use when working a live capture-the-flag event — opening a CTF, enumerating its challenges, deciding what to attack, tracking state across many challenges, and knowing when to abandon one. Covers timezone conversion, flag formats, and scoreboard discipline.
---

# Working an event

## Prepare before the clock starts

**One command runs the whole chain** — toolchain, rehearsal and every platform:

```bash
~/.ctf/venv/bin/python "$DSH_HOME/.agent-presets/ctf-operator/tools/ctfready.py" \
  --target https://ctf.first.example --cookie "session=..." \
  --target https://ctf.second.example --cookie "session=..."
```

It reports the toolchain state, the drill result, and for each platform your
identity, team, the **real start/end in local time**, and whether the CSRF scrape
succeeds — then prints a single **GO / NO-GO**. Run it the night before, and
again at T-15min. Add `--quick` to skip the rehearsal when you only want the
platform window confirmed.

Re-run `recon` on each platform as the start approaches: the countdown is the
authoritative answer to "has it begun", and it is cheaper than refreshing a
browser.

The individual steps, if you need to run one alone:

```bash
python3 "$DSH_HOME/.agent-presets/ctf-operator/tools/ctfpreflight.py"   # toolchain
~/.ctf/venv/bin/python ".../tools/ctfrehearsal.py"                      # techniques
python3 ".../tools/ctfctfd.py" --url <platform> --cookie <ck> recon    # platform
```

Run the preflight check during preparation, never mid-challenge:

```bash
python3 "$DSH_HOME/.agent-presets/ctf-operator/tools/ctfpreflight.py"
```

It reports every CLI tool and Python module with the exact command that fixes a
gap, and exits non-zero if a critical tool is missing. A missing module found at
minute two costs two minutes; found at hour six it costs the challenge.

Then rehearse the playbook itself — this builds throwaway fixtures and runs the
actual techniques (banner mining, digest oracle, LSB stego, z3, pcap, cyclic
offset, ROPgadget, pwntools) against them:

```bash
~/.ctf/venv/bin/python "$DSH_HOME/.agent-presets/ctf-operator/tools/ctfrehearsal.py"
```

17/17 passing means the environment can execute what the skills describe. A
failing drill is a real gap — fix it now, not mid-event. Documentation that has
never been executed is only a hypothesis.

### Warm up on a drill you cannot cheat at

Before a real event, run one full practice cycle end to end:

```bash
~/.ctf/venv/bin/python "$DSH_HOME/.agent-presets/ctf-operator/tools/ctfdrill.py" setup --dir ~/ctfdrill
~/.ctf/venv/bin/python ".../ctfdrill.py" serve --dir ~/ctfdrill --port 8899 &
```

It generates five challenges (rev, stego, crypto, forensics, web) whose flags are
**randomly generated and never written to disk** — each exists only inside its
artifact and the scoring server's memory, so the only way to score is to solve
them for real. Then work them the way an event is worked: read the challenge list
off the API, solve, and submit through `ctfsub.py` with a `--verified` claim.

This is the rehearsal that catches *integration* gaps — a technique that works in
isolation but not under the real submission flow. Confirm all four outcome paths
behave: a correct flag scores, a wrong flag decrements `attemptsLeft` without
marking solved, an already-solved challenge short-circuits locally without a
network call, and a closed event refuses everything.

Start the drill's web challenge (`~/ctfdrill/web/server.py`) to exercise the XXE
sink behind its WAF. The answer key at `~/ctfdrill/.answerkey.json` exists only so
the scoring server can load it — **do not open it while drilling**, and check
yourself against `ctfdrill.py verify` only after solving.

**Use the CTF venv for all Python tooling on this machine:**

```bash
~/.ctf/venv/bin/python solve.py          # pwntools, pycryptodome, z3, gmpy2,
                                         # Pillow, numpy, scapy, capstone,
                                         # pyelftools, volatility3, ROPgadget...
source ~/.ctf/venv/bin/activate
```

The system Python has almost none of it and no `pip`; the venv is where the
toolchain lives, and `checksec`, `ROPgadget`, `vol`, `zsteg` and the pwntools
CLIs are all in `~/.ctf/venv/bin`. Rebuild it with:

```bash
uv venv ~/.ctf/venv
uv pip install --python ~/.ctf/venv/bin/python pwntools pycryptodome z3-solver \
  gmpy2 pillow numpy scapy capstone pyelftools sympy volatility3 ROPgadget \
  hashpumpy oletools
```

Prefer **writing a small script over installing a tool** when the tool is
missing: a 30-line Python solve using the venv beats twenty minutes fighting a
package manager, and it is reproducible for the writeup.

## Open cleanly

Load `ctf-platform-ops` alongside this skill; it covers reading your own event
data, submitting safely, and attempt budgets.

Record, before touching a challenge:

- **Exact window in the user's local time.** Convert, then convert again. A
  CTF announced in UTC ends at a different local clock than it started; get this
  wrong and you lose hours. `python3 -c "from datetime import datetime,timezone;
  from zoneinfo import ZoneInfo; print(datetime.fromtimestamp(1758267000,
  timezone.utc).astimezone(ZoneInfo('Asia/Kathmandu')))"` beats arithmetic.
- **Read the end time from the platform, not from the announcement.** Query the
  event settings through the site's own API and write the exact UTC instant into
  your notes. Then **re-read it every hour and again in the final 30 minutes** —
  published end times drift, and an assumed end time is how you either stop
  working with time left or lose a challenge window you were about to win.
- **The qualification cutoff**, if the event advances a fixed number of teams.
  That rank is the target. Track the gap to it, not your distance from rank 1.
- **Flag format.** Usually `prefix{...}`. One challenge often breaks it
  deliberately. Submit flags **exactly** as emitted — no trimming, no newline.
- **Team size** and whether solo is allowed.
- **Scoring**: dynamic (decays with solves) vs static, and whether first blood
  scores. Dynamic scoring means early solves are worth far more.

## Load the pattern index first

`ctf-writeup-patterns` holds the recurring technique patterns distilled from 30
real writeups — what class of bug a given setup usually hides, and the
heuristics that repeatedly decide challenges (the representation validated is
not the representation executed; classify before decrypting; instrument the
original rather than reimplementing it; silence is a signal). Skim it before
triage. It is an index with sources, so follow a link when a pattern matches
rather than guessing from the summary.

## Enumerate before attacking

List every challenge with category and points. Then rank by
**points ÷ estimated effort**, not by points alone — a 500-point pwn you cannot
finish is worth zero, while three 100-point web challenges are 300.

Read every challenge's description before starting any. They cross-reference
each other more often than you expect, and one often hands you another's key.

## Keep a working file per challenge

```
challenges/<category>/<name>/
  notes.md      # what you tried, what happened, the exact output
  files/        # the artifacts, unmodified
  solve.py      # the exploit / decode script
  flag.txt      # the flag, exactly as emitted
```

Log negative results too. "Tried X, got Y" is what stops you retrying X in an
hour. When you are stuck, the note is what lets someone else help.

**Never edit the originals.** Copy, then work on the copy. A corrupted artifact
with no pristine source is an unrecoverable challenge.

## Triage rules that save events

- **Timebox.** 20–30 minutes with no progress → write down where you stopped and
  move on. Coming back later with fresh eyes works; grinding does not.
- **Do the easy categories first, across the board.** Momentum and scoreboard
  position matter, and easy flags are often prerequisites for hard ones.
- **Check the scoreboard** for which challenges others are solving — a challenge
  with zero solves mid-event is usually broken, not hard. Report it; don't burn
  the event on it.
- **Suspect a broken challenge** after exhausting the obvious path. Say so
  explicitly rather than assuming you are missing something.
- **Never send a burst at a lockout-protected endpoint.** One attempt, read the
  response, then decide. Parallel retries extend the lock and can push it past
  the end of the event. See `ctf-platform-ops` — this mistake alone has cost a
  fully-solved 3,000-point challenge.
- **Do not attack the platform.** Reading your own challenge list, score, and
  event clock through the site's own API is normal play and is encouraged.
  Scanning, flooding, auth-bypassing, brute-forcing flag formats, or reaching
  other teams' data is disqualifying. The line is drawn in `ctf-platform-ops`.

## Delegation: bounded, and consolidated or it did not happen

Subagents are for **parallel, independent, bounded** work — one challenge each,
or one artifact each. They are not a way to feel busy, and a large fleet is not
a strategy.

- **Budget the fleet.** Roughly one agent per genuinely independent workstream,
  plus a couple of second-opinion agents on the hardest challenge. Dozens of
  agents on the same challenge duplicate effort, hammer shared targets, and
  produce reports nobody reads. A fleet of hundreds has produced zero
  additional points.
- **Give each agent a bounded question** with a deliverable: "recover the key
  from this binary, write the script to a file, report the key or the exact
  blocker." Not "solve this challenge."
- **Write results into the shared ledger the moment they land.** An agent whose
  finding stays in its own transcript is worthless — worse, you will re-derive
  it an hour later. Consolidation is the work; delegation without it is waste.
- **Independent verification is the one thing worth an extra agent.** When a
  subagent claims a flag, a key, or a broken challenge, re-verify it yourself
  against the live target before you act on it. Agents confidently report
  success that does not survive a second check, and a wrong "solved" costs far
  more than a slow one.
- **Watch for duplicate effort.** Before spawning, grep your own notes for that
  challenge. The most common waste is three agents rediscovering the same dead
  end.
- **Kill agents that stopped mattering.** Track their ids; stop them when the
  challenge closes. A stale agent still holding a lockout-protected or
  rate-limited target will keep burning your budget.

## Reporting progress

Give the user: what is solved, what is in progress, what you are blocked on, and
the next single action. Not a wall of narration.
