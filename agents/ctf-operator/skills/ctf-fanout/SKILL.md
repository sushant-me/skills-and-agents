---
name: ctf-fanout
description: Use to parallelise CTF work across subagents — board triage while you solve, several independent challenges at once, or an independent re-derivation of a flag before it is submitted. Provides the bounded agent roles (scout, solver, verifier, scribe) as ready-to-paste prompts, the workflow() fan-out script for whole-board triage, and the rules that stop a swarm from corrupting your ledger or tripping platform rate limits. Load when you have more than two solvable-looking challenges, or when a claimed flag needs independent confirmation.
---

# Fan-out: several agents, one ledger, no swarm

Delegation is how a finite attention budget covers a finals board. It is also
how teams lose an event: agents that duplicate each other, agents that submit
to the platform and burn a budget you cannot see, agents whose claimed flags
nobody re-checked.

The rule that makes fan-out safe: **agents discover and derive; the parent
submits.** One process owns the platform credentials, the attempt ledger, and
the decision to spend.

## 1. The roles

Four roles cover a finals board. Spawn the narrowest one that fits, and give
every agent a *bounded* deliverable.

### `scout` — board triage, no solving
> You are doing CTF board triage only. Do not solve anything and do not submit
> anything. Working directory: `<event dir>`.
> 1. Enumerate every challenge: name, category, difficulty, current live point
>    value, solved/unsolved, and any hint price.
> 2. For each, record the artefacts shipped (files, URLs, endpoints) and one
>    line on what the challenge appears to be asking.
> 3. Rank by `value x apparent-solvability / estimated minutes`, and put the
>    two or three you think are cheapest-per-point at the top.
> 4. Flag any challenge that shares an author, stamp, file format, or container
>    layout with another — that is a family, and families solve together.
> Write the result to `TRIAGE.md`. Do not open a challenge's internals beyond
> what is needed to classify it.

### `solver-<category>` — one challenge, deep
> Solve exactly this one challenge: `<name>` at `<path/URL>`. Do not touch any
> other challenge. Working directory: `<challenge dir>`.
> Method: state your hypothesis before testing it; prefer one tested hypothesis
> over a payload spray; record what did **not** work and why, in `NOTES.md`, as
> you go.
> Deliver: the candidate flag, the **exact command or script** that produces it
> from the shipped artefacts, and the raw output showing it.
> Do **not** submit to the platform, and do not guess a flag you cannot
> reproduce. If you cannot derive it, say so and hand back your partial
> findings — a precise dead end is a real result.

### `verifier` — independent re-derivation
Spawn this before acting on **any** flag another agent produced. This is the
highest-value agent on the roster: it is what stops a plausible fabrication
from reaching a credibility-scored platform.
> Independently verify this claimed flag: `<flag>` for challenge `<name>`.
> You have the shipped artefacts at `<path>`. **Ignore the claimant's method** —
> do not read their scripts first. Derive the flag yourself from the artefacts.
> Then compare. Report exactly one of: `CONFIRMED` (with your own reproduction
> command and output), `REFUTED` (with what you got instead), or `INCONCLUSIVE`
> (with what is missing). Never report CONFIRMED on the basis of agreement
> between two agents who shared a method.

### `scribe` — turn a solve into evidence
> For solved challenge `<name>`, produce the write-up entry and evidence list.
> Inputs: the challenge directory, `NOTES.md`, and the accepted flag recorded in
> the team ledger. Output: a markdown section in the team's voice (first person,
> the actual account name), covering what the challenge was, the method, the
> exact derivation, and a bullet list of `path — what it proves` evidence.
> Quote the accepted flag verbatim from the ledger. Do not invent a step that is
> not in the notes; if the derivation is incomplete, say so in one sentence.

## 2. Fan-out a whole board with one workflow

`workflow()` runs a script that fans independent work out and returns structured
results — the right tool for triaging 40 challenges without 40 turns. Keep the
schema small; you want triage data, not prose.

**A ready-made version travels with this preset** at
`tools/fanout/board-triage.js` — pass its contents as the `script` argument,
with `args = { challenges: [...] }`. Build that list from the platform client
(`tools/ctfctfd.py ... list` prints id / category / pts / solved / name), keeping
only the unsolved cards. It returns a `workOrder` ranked by points-per-minute,
the `families` that should be solved together, and the cards the scouts judged
unsolvable. The shape it uses is shown below so you can adapt it.

```javascript
phase("triage")
const list = args.challenges            // [{name, category, path, value}]

const ranked = await pipeline(
  list,
  // stage 1: one scout per challenge, structured output only
  async (_prev, c) => agent(
    `CTF triage only. Do not solve, do not submit. Challenge "${c.name}" ` +
    `(${c.category}, ${c.value} pts) at ${c.path}. ` +
    `Report: what it asks, artefacts shipped, the single most likely attack ` +
    `class, estimated minutes, and whether it shares a family/stamp/format ` +
    `with a sibling. Be terse.`,
    {
      label: `triage:${c.name}`,
      phase: "triage",
      schema: {
        type: "object",
        additionalProperties: false,
        required: ["asks", "attack", "minutes", "solvable"],
        properties: {
          asks:     { type: "string" },
          artefacts:{ type: "array", items: { type: "string" } },
          attack:   { type: "string" },
          family:   { type: "string" },
          minutes:  { type: "number" },
          solvable: { type: "string", enum: ["yes", "maybe", "no"] },
        },
      },
    },
  ),
  // stage 2: score it, no barrier
  async (t, c) => t && ({
    name: c.name, value: c.value, ...t,
    score: (t.solvable === "no" ? 0 : c.value) / Math.max(t.minutes, 1),
  }),
)

log(`triaged ${ranked.filter(Boolean).length}/${list.length}`)
return ranked.filter(Boolean).sort((a, b) => b.score - a.score)
```

Then work the returned list **top-down yourself**, spawning `solver-*`-style
children only for the ones you are not doing, and a `verifier` for every flag
that comes back.

## 3. Rules that keep a fan-out from costing you the event

- **The parent owns the platform.** No child gets credentials, and no child
  submits. A child that submits can burn an `attemptsLeft` budget you cannot
  see, and on a terminal-locked card that ends the challenge for the team.
- **Bound each child to one challenge or one artefact.** "Investigate the
  board" is a swarm instruction; "solve stage 22" is a unit of work.
- **Never parallel-request a rate-limited host.** Children share the network
  path. Ten agents hitting one challenge host trips throttles and, on some
  boards, the platform's own security check — which blocks reading as well as
  submitting.
- **Verify before you spend.** A `verifier`'s `CONFIRMED` with its own
  reproduction outranks the claimant's own confidence. `REFUTED` means you just
  avoided a credibility hit.
- **Consolidate immediately.** A finding that exists only in a child's context
  is worthless the moment that child ends. Every child writes to the shared
  ledger/challenge directory *before* it reports.
- **Prefer one strong child over many weak ones.** On a small board, three
  focused agents beat twelve shallow ones; on a finals board with 40 challenges
  and hours of runway, breadth in *triage* and depth in *solving* is the right
  split.
- **Check descendants before you finish.** Collect or stop every agent you
  started; a child still running when you move on is a source of duplicate
  submissions and stale claims.

## 4. Worked pattern: an Insane card with a team of three

1. `scout` returns that the card ships a register of 16 near-identical flags
   (load `ctf-register-family`) — so the work is *selection*, not crypto.
2. `solver-<category>` derives the documented integer from the artefact and the
   row it selects.
3. `verifier` re-derives the selector from scratch, ignoring the solver's
   script, and reproduces the same row.
4. Parent submits through `ctfsub.py` with `--verified "selector N mod 16
   reproduced independently by a second agent"`, and archives the accepted
   string.
5. `scribe` writes the entry while the next card is already being triaged.

That is four bounded agents and one submission, on a card that a single agent
would have spent an hour guessing at.
