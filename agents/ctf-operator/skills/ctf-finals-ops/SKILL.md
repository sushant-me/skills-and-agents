---
name: ctf-finals-ops
description: Use for a CTF FINAL/endgame round rather than a qualifier — a board of many independent challenges with dynamic scoring, paid hints, per-card attempt budgets, and a ranked final table. Covers the four mechanics that decide finals (value decay, hint economics, terminal attempt locks, cross-account budget), the evidence discipline that a post-event write-up depends on, and the score reconciliation you will be asked to defend. Load it at the start of any finals round, and again before the first hint purchase or the first submission.
---

# Finals operations: the round is scored, not just solved

A qualifier asks *can you solve it*. A final asks *can you solve it, in order,
without spending more than it is worth, and can you prove it afterwards*. Four
mechanics decide the ranking, and all four are about resource accounting rather
than skill. This skill is the accounting.

## 1. Dynamic scoring — read the value, never assume it

Card values on a finals board **decay as more teams solve them**, and the
advertised value is not the value you will be credited.

- Read the live value from the board/API at the moment you submit.
- **High-value cards decay fastest and hardest.** A 2000-point Insane card is
  worth 2000 only to the first solver or two; by the fifth solve it can be a
  third of that. This is why an early solve on an expensive card is worth
  several late solves on cheap ones.
- Triage by `value x probability-of-solving / expected minutes`, and re-triage
  as the board moves. A card you were saving can halve while you finish a
  cheaper one.
- First blood is worth chasing on expensive cards specifically because it is
  the only time you get full value. Two Insane cards solved at full value can
  beat ten medium cards solved late.

Do not plan around the number on the card. Plan around the number the board is
showing right now, and re-check it before you commit an hour.

## 2. Hint economics — a hint is a purchase, not a freebie

Some finals boards sell hints, and the price is **deducted from your own
score**. Treat it as a purchase decision with a clear rule:

> Buy the hint when `hint cost < expected value of the card x probability the
> hint converts it`, and when you have already spent more time stuck than the
> card is worth.

- On an Insane card worth 2000 that you are stuck on, a 500-point hint that
  converts it is a **four-to-one return**. Buy it. Refusing a 500 hint to
  protect a 500 score while a 2000 card sits one parameter away is the losing
  play.
- Read the hint **literally**. They are usually written to name the exact thing
  you have been assuming wrongly. A hint that says *"look closely at the probe
  parameter"* means the parameter name matters — not that you should look
  harder at the parameter's value.
- The best hint of an event is the one that tells you a card you wrote off as
  *unsolvable as deployed* is actually solvable. Buy that one immediately.
- **Record every hint purchase** with its cost and the card it was for. It must
  appear in the final score reconciliation (§5) or your arithmetic will not
  close.

## 3. Attempt budgets and terminal locks — the budget is a team resource

Finals boards commonly cap submissions per card and report `attemptsLeft` in
the response. **At zero the card is terminal: you cannot submit it again even
after you solve it.**

- Read `attemptsLeft` from every response and write it into the ledger.
- **Never send parallel attempts at a budgeted endpoint.** A burst can consume
  the budget on transport errors and leave you locked out with the answer in
  hand.
- **Rate limits eat attempts.** On a throttled board an error response may or
  may not have consumed an attempt. On a transport error, check status before
  retrying — never blind-retry.
- **Spread the budget across the team.** Per-card budgets are usually
  per-account. A card terminal-locked on one account is still open on a
  teammate's. Real case: two OSINT cards were terminal-locked on the primary
  account (the free formatting hints were published only *after* our budget was
  gone) and were closed by a teammate submitting from theirs.
- If an organiser resets another team's counters, ask for yours too — but do
  not plan on it.
- `alreadySolved: true` means the card was already credited, often on a shared
  or teammate account. That is a **credit, not a failure** — record which
  account took it and move on.

## 4. Evidence discipline — this is where finals are actually lost

The single most common finals failure is not a wrong flag. It is **not
capturing the accepted string at the moment it was accepted**.

On one finals run, five of forty cards ended up documented only as *"the
accepted value was never recorded"*, because submissions went through a browser
and ad-hoc scripts that did not archive what they typed. The solves were real
and credited; the evidence was gone. The post-event write-up had to be hedged on
those entries, and a reviewer cannot distinguish that from a guess.

So, mechanically:

1. **Route every submission through one client that appends to one ledger** —
   the bundled `tools/ctfsub.py` exists for this. Use `--verified "<how>"`; do
   not submit from a scratch `curl`.
2. Each ledger row: `challenge | candidate | result | timestamp |
   attemptsLeft | verified-how`.
3. **On acceptance, store the exact accepted string** as returned by the
   server, not the string you believe you sent. Wrapper case and zero-versus-
   letter-O differ between cards, and the server's copy is the only one that
   counts.
4. Keep **one evidence directory per card** (`README`/`FINDINGS` +
   the scripts + the raw response) while you work. Reconstructing this after
   the event from memory is impossible; doing it as you go costs seconds.
5. Capture the artefacts a write-up needs **as you go**: the success response,
   the live standings screenshot, the derivation output. They are unrecoverable
   later.

## 5. Reconcile the score you will be asked to defend

The final table and your own arithmetic will disagree unless you account for
every deduction. Keep the identities explicit:

```
board value of the cards you closed      = base
  - hint purchases                       = hint spend
  - dynamic decay already reflected      = (read, do not estimate)
  ------------------------------------------------
  = the credited score on the final table
```

Worked example from a real finals board: 40 cards closed with a base board
value of **17,350**; one hint bought for **500**; credited **16,850**. The 500
difference was *entirely* the hint — an earlier draft attributed it to
"dynamic scoring", which did not survive contact with the arithmetic.

Two more reconciliation rules:

- **Per-solve attribution is less reliable than your own ledger.** A shared
  account, or a platform that credits the *last* solver, will disagree with who
  actually solved what. Keep your own record and say so plainly if they differ.
- **State the gap to first place honestly.** "We closed more cards than the
  winners but lost on points because their cards were worth more at the close"
  is a defensible sentence. "We were robbed" is not, and a reviewer will check.

## 6. The write-up is a scored deliverable, not an afterthought

Finals rounds commonly require **one report per team, submitted by a hard
deadline after the event**, and it is often judged by people who were not
watching the board.

- Build the report pipeline **during** the event, not after. A markdown source,
  a converter, and a screenshot helper should exist before the last hour.
- The bundled `tools/writeup-pipeline/` (see the `ctf-writeup-production`
  skill) does markdown → styled HTML → A4 PDF with proof images.
- Every claim should point at a file: `challenge/scripts/artifact.ext` plus a
  one-line reason it proves the claim. A reviewer verifying your work should
  never have to guess where something came from.
- Write in the voice of the people who did the work, in first person, with the
  team's own account names. Do not sand it into a neutral tone — the texture is
  evidence that humans did it.
- **Do not invent certainty you do not have.** If the accepted string was not
  captured, say that in one sentence and move on. A stated gap is credible; a
  confident invention that a judge can falsify is not.

## 7. Checklist

```
[ ] live card values read from the board, not the challenge list
[ ] ledger client in use for EVERY submission (no scratch curl)
[ ] accepted string archived verbatim at acceptance time
[ ] attemptsLeft recorded after every response
[ ] no parallel attempts at a budgeted endpoint
[ ] hint purchases logged with cost
[ ] per-card evidence dir started while solving
[ ] standings + success screenshots captured during the event
[ ] score reconciliation arithmetic closes (base - hints = credited)
[ ] report pipeline built before the deadline, not after
```
