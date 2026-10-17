---
name: ctf-rules-check
description: Use BEFORE solving any challenge in a live CTF, and whenever asked to compete in, assist with, or "win" a capture-the-flag event. Establishes whether that event permits AI/LLM assistance, forbids it, or is silent — and what its account rules are — so participation stays legitimate.
---

# Rules check: do this first

A CTF measures the skill of the account that submits. An assistant that solves
challenges under an account whose rules forbid it is not "helping" — it is
taking score and prizes from people playing straight, and it puts the
account-holder's recognition (the thing most people are actually after) at risk
of disqualification.

**This check comes before the first challenge is opened.** It is cheap and it
decides everything downstream.

## 1. Find the rules

Look, in this order, and stop when you find them:

1. `https://<event-host>/rules`, `/terms`, `/terms-of-service`, `/tos`, `/faq`,
   `/code-of-conduct`. CTFd serves these only if an admin created them, so a
   404 is a real answer: *no published rule*.
2. The organising body's **main** site — not the CTF subdomain. Terms often live
   there (`/terms-of-service/`) and still bind the competition.
3. The event's **CTFtime** page (`https://ctftime.org/event/<id>`) and its Discord.
4. The registration form itself. A mandatory checkbox reading *"I agree to the
   … rules of engagement"* means rules exist **and are binding** — if you cannot
   read them anywhere, say so; do not assume they are permissive.

> Real case: Null Origin's register form requires agreeing to "the Null Origin
> rules of engagement", but no rules page exists on the site at all. Rules you
> are made to agree to and cannot read are a reason to **ask in their Discord**,
> not a reason to proceed — and here asking worked: the organisers sent the
> "NULL_Origin Capture The Flag: Official Rules of Engagement" PDF, which is now
> the source for every Null Origin claim below. **Ask; do not infer.**

## 2. Read for exactly these four things

| Look for | It means |
|---|---|
| An explicit AI / LLM / "tools" clause | **Decisive.** Quote it verbatim in your answer. |
| "unfair competition", "fair play", "spirit of the competition" | Broad, but it covers hidden AI solving. Treat as **no**. |
| "individual", "non-transferable", "one account per person" | You may not log in as the account-holder or drive their session. |
| Screen recording, proctoring, "viewing access of their screens" | Anything you do may become visible; a hidden workflow is a liability. |

## 3. Decide

| Finding | Verdict |
|---|---|
| **Explicitly permits** AI/LLMs/tools of any kind | **Go.** Work the challenges openly. |
| **Explicitly forbids** | **Stop.** Do not solve, do not submit. |
| **Silent** (no rules published) | **Ask the organisers first.** Silence is not permission. |
| **Silent in the ToS but has an "unfair competition" clause** | **Not an answer by itself.** Find the competition rules document and ask in the Discord before deciding — see the Cyber League correction below. |

### Check BOTH documents — a ToS "fair play" clause is not the AI policy

This is the correction that matters most, because getting it wrong is expensive.

**Cyber League appeared to forbid AI — and that was wrong.** Its Terms of Service
(`cyberleague.co/terms-of-service/`) says, verbatim:

> *"the adoption of unfair competition practises or anything similar are strictly
> forbidden"* … *"Login information is individual and non-transferable."*

A blanket fair-play clause, no AI mention anywhere on the public site,
`cyberleague.co/rules` a 404, and no rules page in the CTFd. I concluded
"forbidden". The competition's **own rules document** — which is not linked from
the public site — carries a section that settles it the other way:

> **3.1 AI Tool Authorization** — *"Participants are granted full access to
> Artificial Intelligence tools (e.g., ChatGPT, Claude, Gemini, GitHub Copilot)
> to assist in code analysis, exploit development, or general troubleshooting.
> We encourage the use of these tools as a 'force multiplier.'"*

and the organiser confirmed it in their Discord: *"yes it available many team
have requested so we have given them to use their LLM."*

**So: read the Terms of Service AND the competition rules document, and ask in
the Discord.** A generic "unfair competition" clause settles nothing on its own —
it is boilerplate that nearly every event ships, and the AI answer usually lives
in a separate rules page, a pinned Discord message, or a PDF. Only an absence in
**all** of those means "ask".

### The three outcomes, with real examples

| Event | Where the answer lived | Verdict |
|---|---|---|
| **WATCHLIST** | `/rules` — explicit | **Permitted**: *"Tools of any kind are permitted… This includes large language models"* |
| **Cyber League** | rules doc §3.1 **+** organiser in Discord | **Permitted**: *"granted full access to Artificial Intelligence tools… a 'force multiplier'"* |
| **Null Origin** | official rule book PDF, sent by the organisers | **Permitted** — §III *"AI Integration & Credibility Policy"*: *"Participants are encouraged to leverage AI as a force multiplier for code analysis and exploit development."* |

Note the shape: the two permissive answers arrived by **two different routes**,
and the ToS was misleading in both directions. Read widely, then ask.

**All three events now permit AI — but by three different routes, and the
documents are not interchangeable.** Note the numbering: the Null Origin rule
book uses roman sections (I–IV, with §III covering AI), whereas the earlier
excerpt circulated for Cyber League used decimal subsections (3.1, 3.2) and a
bullet named *"Hallucination Penalty"* that does **not** appear in the Null
Origin PDF. They are **two different documents with very similar wording**, so
**cite the document you actually read, for the event you actually checked.** Do
not carry one event's rules across to another — the language overlaps enough that
this is an easy and costly mistake.

## 4. Report the verdict before working

State, in one line each: the event, where you found the rules (URL), the exact
clause, and the verdict. Then proceed, or explain what you will do instead.

## 5. If AI is permitted, the flags still have to be real

Cyber League's rules pair the permission with a penalty — and it targets exactly
the failure mode an AI assistant has:

> **3.2 The Credibility Score Metric** — *"Submitting incorrect flags,
> hallucinated exploits, or invalid automated data generated by AI will result in
> an immediate decrease in your Credibility Score."*
>
> *"AI tools often generate plausible-looking but entirely fictitious strings or
> payloads. Submitting these 'hallucinations' to the scoring engine is considered
> a failure of verification and will be penalized more heavily than standard
> incorrect guesses."*

Null Origin states the stakes more bluntly still: *"The Credibility Score affects
final standings, serving as a **tie-breaker** and a potential **multiplier for
total points**."* So a hallucinated submission does not merely cost one flag — it
can **scale down everything else you scored.**

**A wrong flag is a normal loss. A confident, invented flag is worse than a wrong
guess, and can be worse than every other flag you solved.** That inverts the
usual instinct to always submit something.

Operating rules:

- **Never submit a flag you have not reproduced.** Re-derive it from the
  challenge, or verify it against the program's own check.
- **State confidence explicitly** when handing a candidate to the person who
  presses submit. "This decodes cleanly and round-trips against the original
  ciphertext" is a different claim from "this looks like the right shape."
- **When unsure, say so and keep working.** Do not offer a guess dressed as an
  answer — that is precisely what the rule penalises.
- If asked to submit an unverified candidate anyway, say plainly what is
  unverified about it.

## What is fine everywhere

- **Preparation**: practice targets, technique drilling, tooling setup, reading
  public writeups of *retired* challenges.
- **Explaining** a concept or a technique the person is stuck on.
- **Post-event writeups**, once the event has ended and its rules permit
  discussing solutions.

## Null Origin's other rules (from the same PDF)

- **No flag sharing**: *"Sharing flags, providing hints, or discussing active
  challenge solutions with other competitors is strictly prohibited."* This
  binds *us*: help this team only, never another.
- **Individual effort**: *"Unless registered as a team, all work must be the
  result of individual effort and verification."* Null Origin is registered as a
  team (*Team Roamers*), and §III permits AI — so AI assistance is authorised;
  this clause is about not pooling with **other** teams.
- **Infrastructure is off-limits**: do not attack the scoreboard, challenge
  servers, or hosting. *"Attacks should be directed only at the specified
  challenge targets."*
- **Denial of service prohibited** unless a challenge explicitly requires it,
  and contact admins if your tooling causes performance issues.
- Report platform bugs to organisers via official channels.

## What is never fine

- Logging in with someone else's credentials, or driving their authenticated
  session, where the rules make login non-transferable.
- Solving or submitting under an account whose event forbids assistance.
- Bypassing a CAPTCHA or any other human-verification control. That is a gate
  addressed to the person, not an obstacle to route around.
- Sharing flags with, or receiving them from, another team where that is banned.
