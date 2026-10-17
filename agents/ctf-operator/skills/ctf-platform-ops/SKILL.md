---
name: ctf-platform-ops
description: Use when working a live CTF platform — reading your own challenge/score data through the site's own API, submitting flags safely, respecting attempt budgets and account lockouts, and verifying a flag offline before spending a submission. Load this before your first submission of an event.
---

# Platform operations

Everything here is about **not losing points you have already earned**. Reading a
challenge correctly and then fumbling the submission is the most common way a
strong solve evaporates.

## Read your own data through the app's own API

The frontend is authorized for you. The calls your own browser makes to render
the challenge list, your score, and the event clock are **your data**, and using
them directly is normal play — it is what the UI does. This is the single
highest-leverage five minutes of an event.

What to extract, early:

- **Exact challenge list**: title, category, points, description, attachments.
  Better than clicking through the UI, and it lets you rank offline.
- **Attempt budgets** per challenge (`maxAttempts`) — see lockouts below.
- **The true event window**. Do not trust the announcement text or your own
  arithmetic. Read the end time from the platform and re-read it as the end
  approaches. Getting this wrong by even five minutes has cost a tournament.
- **Solve counts** — a challenge nobody has solved mid-event is more often
  broken than brilliant.

How:

1. Open the site's own network traffic (devtools, or the browser profile's
   storage) and find the backend it talks to.
2. Reuse the session token **the app already stores for you** — you are that
   user, and this is your session.
3. Query the same endpoints the frontend does.

**The line that must not be crossed.** Reading your own authorized data is play.
These are not, in any event, ever:

- Reading another team's private data, submissions, or flags.
- Denial of service, load testing, or "just checking" with floods.
- Auth bypass, privilege escalation, or reaching admin surfaces on the platform.
- Bypassing a CAPTCHA or any human-verification control.
- Brute-forcing the flag format, or scripting around a rate limit or attempt cap.

If you find yourself reasoning "the platform is also a system, so it is fair
game" — stop. The platform is the referee, not the challenge.

## Find the real submission path

The working submit call is **whatever the page actually invokes**, which is often
not the documented API and not the one you would guess. Capture it from the
frontend rather than guessing names; a wrong guess looks like a wrong flag and
wastes an attempt.

Read the response contract carefully and record it. A good submit endpoint tells
you several distinct things, and conflating them wastes attempts:

| response | meaning | action |
|---|---|---|
| accepted / correct | solved | record flag + points, move on |
| already solved | you solved it before | stop; do not resubmit |
| wrong, `attemptsLeft: N` | a real miss | decrement your ledger, rethink |
| rate-limited | too fast | back off for the stated delay, then retry once |
| event ended | scoring is closed | stop submitting entirely |

Treat `already solved` as success, not failure — it means your notes are stale,
not that the flag is wrong.

## Attempt budgets and lockouts — the rule that decides events

**On any endpoint protected by account lockout, send exactly ONE attempt, read
the response, then decide. Never fire parallel attempts.**

Lockouts are usually store-backed and **every failed attempt extends them**. A
burst of ten "quick checks" does not cost one attempt — it can push the lock
past the end of the event, converting a solved challenge into a zero. This is
not hypothetical; it is the single most expensive mistake in this playbook.

Before spending an attempt on a lockout-protected target:

1. Read `lockUntil` from the last response and **compare it to the event end**.
   If the lock outlasts the close, the challenge is already lost — stop, do not
   probe further.
2. Check your ledger for attempts already spent on this challenge/account.
3. Send one attempt. Record it immediately.

### A lock does not expire — it re-arms, and the penalty ratchets

Measured on a live target: the lock was allowed to expire, a **single** attempt
was then sent, and it returned a **longer** lock than before (4.5 minutes →
15 minutes) without ever evaluating the credential. Repeated failures escalate.

The practical consequences are severe and non-obvious:

- **Waiting out a lock does not buy you an attempt.** The next request re-arms
  it, and the window grows. A locked account is a ratchet, not a timer.
- **A guessing strategy against a lockout target is therefore self-defeating**:
  the first wrong guess can make the correct one unreachable for the rest of the
  event, even if you find it later.
- **The only attempt worth making is one you are confident is correct.** Get the
  credential from the challenge itself (source, config, a leak, an oracle) and
  verify it offline first. "Try it and see" has no upside here and an
  event-ending downside.
- **Once armed past the close, the challenge is gone.** Say so plainly and spend
  the time elsewhere rather than refreshing.

This is the single most expensive mistake in this playbook: a fully solved
3,000-point challenge became a zero because the credential was tested in a burst
instead of being established first.

Keep a ledger file and never double-spend an attempt. Two columns matter:
attempts spent, and attempts remaining as reported by the server. When the
server reports a budget, trust the server, not your own count.

## Verify offline before you submit

A submission spent is a submission gone. Many challenges ship a way to check a
candidate **without touching the platform** — use it every time:

- **Hash oracles**: a binary embedding `sha256(flag)`, an expected digest, or a
  keyed MAC. Extract the constant and test candidates locally at full speed.
- **Signature / key oracles**: a verifier that validates a flag without
  consuming an attempt.
- **Seal / stage oracles**: endpoints that validate one component and report
  which parts are correct — they let you confirm a fragment rather than gamble
  the whole flag.
- **The author's own `verify` binary** — but **copy it to a scratch directory
  first**. Many self-lock after a few wrong answers (a `.strikes` file next to
  the binary is the giveaway). Never run the original for guesswork.

When an oracle exists, an unverified submission is a mistake even if it turns
out to be right — you spent a resource you did not have to.

## Score math, not vibes

Track three numbers continuously: your score, the cutoff you are chasing (the
rank that qualifies), and the gap. Then spend effort against the gap.

- A 100-point challenge is worthless when the gap is 1,850. Chase the
  high-value unfinished challenges even when they are harder.
- Conversely, when the gap is small, sweeping easy unsolved challenges across
  every category is the fastest route.
- Recompute after every solve. Ranks move while you work; a leaderboard read at
  hour two is fiction at hour ten.

If the event qualifies a fixed number of teams, **the cutoff is the target**,
not first place. Chasing rank 1 while sitting at rank 11 is misallocated effort.

## Record every submission

One append-only ledger for the whole event:

```
<challenge>  <flag>  <result>  <timestamp>  <attemptsLeft>
```

This is what stops you resubmitting a known-bad flag, lets you audit a
suspicious rejection, and tells the next session exactly where you stand. It is
also the artifact that proves what you did.

### Use the bundled client

`tools/ctfsub.py` (beside this skill's preset) implements the rules above so you
do not have to remember them under time pressure. It is single-threaded by
construction, refuses to exceed a server-reported budget, backs off on a
throttle, stops dead once the event ends, and **refuses to submit without a
verification claim**:

```bash
CTF_SUBMIT_URL=<endpoint captured from the frontend> CTF_TOKEN=<session token> \
  python3 "$DSH_HOME/.agent-presets/ctf-operator/tools/ctfsub.py" \
  --ledger ~/ctf/ledger.json submit <challenge_id> '<flag>' \
  --verified "round-trips against the original ciphertext"

python3 .../ctfsub.py --ledger ~/ctf/ledger.json status
```

Exit codes: `0` solved or already-solved · `1` wrong · `2` refused (no
verification claim, event over, budget exhausted, or already solved) · `3`
transient (throttled / auth / transport — resolve before spending another).

**On a transport error the attempt may or may not have landed.** Check `status`
before retrying, and never blind-retry a lockout-protected target.

### If the platform is CTFd, use `ctfctfd.py` instead

Most events — including both of the ones this preset was last prepared for — run
**CTFd**, which differs from a bespoke platform in three ways that silently cost
attempts if you meet them cold:

1. **Every POST needs a CSRF nonce**, embedded in the landing page as
   `window.init.csrfNonce`. Without it the request is rejected in a way that
   looks exactly like a wrong flag.
2. **Submissions are status-coded**, not boolean:
   `{"success":true,"data":{"status":"correct|incorrect|already_solved|paused|ratelimited"}}`.
   Treating `paused` as `incorrect` burns budget on a server-side throttle.
3. **Before the start**, `/api/v1/challenges` returns 403 and a POST returns a
   **bare `{"message":...}` with no `data` key**. That is a refusal, not a
   verdict on your flag — reading it as "wrong" spends an attempt on a challenge
   that was never open.

`tools/ctfctfd.py` handles all three. It scrapes the nonce (with a fallback
scan, because themes emit `window.init` differently and a minifier can move it),
falls back to the API for identity when a theme omits it, and classifies every
CTFd status:

```bash
CTF_COOKIE="session=..." python3 .../tools/ctfctfd.py \
  --url https://ctf.example.com recon          # window, identity, csrf, challenge count
  --url https://ctf.example.com list           # id, category, points, solved
  --url https://ctf.example.com --ledger ~/ctf/ledger.json \
      submit <id> '<flag>' --verified "<how>"
```

Grab the cookie from the browser: DevTools → Network → any request → copy the
`Cookie` header, or read it from the profile. `session=` is the only value that
matters.

**Rehearse it before the event, not during:**

```bash
~/.ctf/venv/bin/python .../tools/ctfctfd_mock.py --port 8897 --live &
python3 .../tools/ctfctfd.py --url http://127.0.0.1:8897 recon
```

The mock is CTFd-faithful: it enforces the CSRF header, hides challenges before
the start, and returns the real status shapes. Running `recon` → `list` →
`submit` against it proves the client works *before* the clock starts. The
correctness of the submission path is the one thing you cannot afford to
discover at minute one.

### The credibility penalty is why the gate exists

Several events — Null Origin and Cyber League among them — pair the permission
for AI assistance with a **Credibility Score** that drops when you submit
"incorrect flags, hallucinated exploits, or invalid automated data generated by
AI". It is not cosmetic: it serves as a **tie-breaker and a multiplier on total
points**, so one invented flag can scale down everything else you scored.

That inverts the usual instinct to always submit something:

- A **wrong** flag is a normal loss.
- A **confident, invented** flag is worse than a wrong guess and can be worse
  than every other flag you solved.

So submit only what you reproduced — re-derived from the challenge, or checked
against the program's own verifier — and pass the verification method along with
the candidate. When you are unsure, say so and keep working rather than offering
a guess dressed as an answer. `--unverified` exists for the rare case where you
mean it, and it says so in the ledger.
