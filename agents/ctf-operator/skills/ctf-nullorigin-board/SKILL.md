---
name: ctf-nullorigin-board
description: Use when playing NullOrigin CTF, its finals, or any board by the same author. Encodes the board's design — chained stages where a flag is the next stage's key, a container whose CRC is the only oracle, stages saturated with confident wrong answers, GF(2) keygen-me reversing with no flag inside any binary, and metas keyed on non-flag internal secrets rather than the flags. Load it before the first stage, not after a wrong submission.
---

# NullOrigin board: play the design, not the challenge

This board is not 34 independent puzzles. It is five chains built by one author
against one thing: **the reflex to run the obvious tool and submit its first
answer.** Every stage ships three or four answers that a competent player finds
in the first two minutes, and exactly one that requires the technique the stage
is actually about.

Consequence, stated once: **an answer you found quickly is a decoy until you
have eliminated it.** The board is engineered so that the confident-fast answer
is wrong, and on a credibility-scored event a wrong submission is more than a
lost flag.

---

## 1. Establish the conventions before you touch stage one

Two conventions carry the stego chain and the author teaches both in-band, once,
early, then never again. Missing them costs the chain.

### The works entry — the only oracle on the stego chain

```
b'PL8' | version: u8 | length: u16 LE | crc32: u32 LE | payload
```

- **The magic plus a passing CRC is the only signal that you have found the
  right channel.** Nothing on the chain tells you whether a *flag* is right
  except whether it opens the next stage. (Scope: this is the *stego* chain's
  rule. Crypto, forensics and reversing do ship `verify` binaries — on those
  stages the verifier is an offline oracle, so use it before submitting, and
  never treat its absence as licence to guess.)
- **No decoy ever sits inside a valid works entry** — with exactly one
  deliberate exception, on stage 37, and it is the nastiest trap on the board.
  So: a flag-shaped string outside a container is a candidate, not an answer.
  The exception is worth knowing exactly, because it is the one place the
  container check *lies*: reading bitplane 0 row-major MSB-first unkeyed from
  pixel 0 — the first order every generic tool tries — yields a complete,
  CRC-correct entry whose flag is **stage 36's real flag with a single
  homoglyph** (`Null0rlgin`, lowercase `l` where the `i` belongs) and whose
  trailing bytes are a **fake seventh share**. Take that share and the inner
  lock simply never opens, with no error and no hint how close you were. The
  container check cannot catch it; **the prefix audit can**, and that is why
  step 2 below is not optional.
- Payload for stages 31–36 is `flag || 0x1F || share`, the share 8 bytes.
  **Keep the share** — nothing in those six stages asks for it, and stage 37
  cannot be opened without all six. Stage 37's payload carries no share of its
  own; stage 38's payload is the flag alone.

### The key schedule

```
k       = SHA-256(previous_flag)            # braces INCLUDED, exact bytes
stream  = SHA-256(k || counter_be32) for counter = 0, 1, 2, ...
          concatenated and truncated to the needed length
payload = ciphertext XOR stream             # octet for octet, from the front
```

Stage 31 is the only unkeyed stage. **Stage 37 needs two keys and neither alone
works:** the ordinary chain key from stage 36's flag, *and* `SHA-256` of all six
mordant shares concatenated in stage order.

### The chain order

`stego: driftwood → safelight → moire → undertone → pentimento → winnow →
mordant → quietus`. Crypto `06→13`, forensics `14→20`, rev `21→27`,
boot2root `00, 28–30`.

---

## 2. The decoy taxonomy — learn it on sight

There are **27 strings on the stego chain alone** that are in flag format and
are not flags. About ten sit in the clear, exactly where the first reflex looks.
Three families:

| Family | What it looks like | Discriminator |
|---|---|---|
| **Plausible-but-wrong content** | Fits the stage theme perfectly; reads as a natural "find" | Is it inside a valid `PL8` entry with a good CRC? If not, it is not the answer |
| **Homoglyph prefixes** | `NullOrigin` (capital O), `Nu110rigin` (digit ones), `Null0rlgin` (lowercase L) | **Check the prefix character by character, every time.** Cheap, and it is the whole test |
| **Right-shape, wrong-run** | Reads like a flag from a neighbouring stage — often the one you just solved | Compare against every flag you already hold |

A decoy can also be a **correct decode of the wrong data** (stage 16:
realtime-sorted logs DTMF-decode cleanly, to the wrong flag). A clean decode is
evidence about the *data*, not about the *answer*.

## 3. The elimination procedure — run it on every candidate

Do not submit the first flag-shaped string. Run this:

1. **Is it inside a valid works entry?** Magic `PL8` **and** CRC passes. If no →
   it is a candidate, not an answer. (Remember the one deliberate exception.)
2. **Prefix audit.** Character by character against `Null0rigin`. Do not eyeball it.
3. **Already-seen check.** Is it a flag from a stage you have already solved?
4. **Channel check.** Did it come from a channel a general-purpose tool models
   (`zsteg`, `steghide`, `binwalk`, metadata)? Past stage 32 that is a decoy by
   construction. Every later channel is one no scanner models: halftone cell
   arrangement, sub-noise-floor DSSS, GIF palette order, chaffing-and-winnowing,
   PNG filter bytes, DEFLATE token choice.
5. **Only then** accept — and for stego, "accept" means *it opens the next stage*.

**State the elimination out loud in your notes.** A candidate you cannot
eliminate is not a flag; it is an open question, and writing it down as an open
question is what stops it becoming a wrong submission twenty minutes later.

**Run the mechanical part of it as a tool, not by eye.** The preset ships
`ctfnulltriage.py`: it does steps 1–3 above without judgement, and adds a fourth
check against the author's writeups when you have them offline, so a candidate
you already hold or one the author has labelled a decoy can never reach the
submitter. Checked over those 103 strings, it convicts none of the seven the
writeups declare as a stage's flag — a screen that occasionally misses a decoy
is useful, one that kills a real flag is not.

```sh
T=~/.dsh/.agent-presets/ctf-operator/tools/ctfnulltriage.py
python3 $T --container /path/to/downloaded/33-moire/plate.png \
           --ledger ~/Work/ctf/NOTES.md \
           --reference /path/to/NullOrigin-CTF-2026-Writeups \
           "Null0rigin{candidate}" "NullOrigin{near_miss}"
```

Exit 0 means at least one candidate is *eligible*, which is not the same as
correct — only the next stage confirms. Exit 2 means everything was convicted or
is unproven, and nobody submits.

### Do this before you solve anything: sweep the board

The container is a *searchable* oracle, and that is the finals move. One command
walks every downloaded artifact and reports every valid works entry it contains —
the channels, the flags, and **all six shares in stage order** — before you know
what any stage's mechanism is:

```sh
python3 $T --scan ~/dl/nullorigin --ledger ~/Work/ctf/NOTES.md
```

It annotates each entry with its own prefix verdict and **refuses the stage-37
poisoned entry's seventh share**, which is otherwise the most expensive mistake on
the board. If an artifact yields more than one entry, the tool says so: on this
board that shape *is* the trap. Point it at the whole download directory on day
one, and again as each stage lands — a share you did not keep costs you the whole
rest of the chain, and this makes keeping it mechanical.

Why the order is 1 before 2, measured rather than asserted: across the author's
writeups there are **103 distinct flag-shaped strings**, and **only 9 have a
prefix that is not exactly `Null0rigin`** — eight of them the homoglyph family,
all convicted outright, plus one code snippet that is not a flag at all.
**The other 94 carry the exact prefix**, so the prefix audit says nothing about
any of them, and 18 of those 94 sit under the author's own `## Decoys` heading.
The prefix audit is cheap and it kills a real family; it is not the test.
**The container is the test.**

## 4. Collection discipline — the metas are not keyed on flags

This is the single highest-value habit on this board, and the one that loses
chains for teams holding every flag.

- **13-lantern (crypto meta)** is keyed by **seven non-flag internal secrets**,
  one reconstructed from each prior stage's own artifact — not the seven flags.
  Holding all seven flags still will not open it. The secrets are recombined by
  secret sharing over the ring **Z/2^64**, not a prime field, which is why
  naive inversion fails; it is solved 2-adically through non-invertible pairwise
  differences.
- **20-nullwatch (forensics meta)** is sealed by `SHA-256(flag)[:8]` of each of
  the six real flags. It cannot be opened from the recoverable byte offsets,
  SSRCs or physical addresses of the prior stages. So **store `SHA-256(flag)[:8]`
  the moment you recover each flag** — and store the real flag, because a decoy
  hashes just as well.
- **27-hourglass (rev meta)** is keyed off all six prior flags plus a four-value
  runtime choreography.

**Rule: after every stage, record the flag, its `SHA-256[:8]`, and any trailing
bytes the stage handed you — before moving on.** Recovering a stage twice costs
more than the bookmark.

## 5. Per-category playbook

### Reverse engineering — no flag exists inside any binary

Verification is a **property check**, never a comparison:

```
accept  iff  A · x == b      over GF(2)
```

`A` is generated at runtime and **is never stored anywhere**; `b` is the only
thing baked in; `A` is full rank, so there is exactly one solution.

- **A memory dump at the moment of comparison yields a matrix, not a string.**
  Static analysis yields a matrix. The route is to *reconstruct* `A`, read `b`,
  and run GF(2) Gaussian elimination — then repeat per layer, seeding each from
  the previous layer's solution.
- **Every stage also ships a second, complete decoy system** whose intended
  unique solution is a valid-ASCII flag with nothing marking it wrong. It is
  reachable by the route static analysis suggests first. Solving it feels
  exactly like solving the real thing.
- **Every stage gates control flow on `SHA-256` over a runtime-computed value.**
  A symbolic engine cannot invert SHA-256 and will stall rather than explore —
  this is deliberate. Real concrete execution is the only way through.
- Traps to expect: `readelf -l` (program headers, what the kernel honours)
  versus `readelf -S` (section headers, what tools read) **disagree** — follow
  the program headers. x87 `FSIN`, 80-bit precision control and MXCSR flush
  behaviour need **real hardware**; no portable IEEE library reproduces them.
- **Layer keys are derived from the `sha512crypt` OUTPUT, never the plaintext
  password** — `hashcat -m 1800`, then key off the hash.

### Forensics — genuine decoys, tool-recoverable

Every stage ships real decoy data: deleted files, plausible tone decodes,
framebuffers that XOR to noise. "Run the obvious tool, take its first answer"
produces a confident wrong flag every time. The real technique is what standard
tooling does not surface by default:

- FAT32: the flag is one bit per **allocated-but-unreferenced** cluster — walk
  the directory chains, record every cluster the walk visits, and the largest
  unvisited run is the channel.
- RTP sharing a port: split by **marker bit, not SSRC**; averaging smears both
  images into noise and the wrong stream decodes cleanly.
- Journals: **write order (`__SEQNUM`) vs wall clock (`__REALTIME_TIMESTAMP`)** —
  a stepped-back clock makes the default sort pick the wrong boot, and the wrong
  boot decodes perfectly.
- Memory images: enumerate page tables and find the mapping **not covered by any
  VMA** the process reports.
- ext4: deleted-but-intact extents disambiguated by **`crtime`**, not size.
- VM clones: an un-reseeded CSPRNG is a **two-time pad** — `keystream =
  ciphertext_A XOR template`.
- pcaps: **the frame timestamps lie.** Cross-check the TCP Timestamp option
  against an independent clock source (a log) before trusting either.

### Crypto — identify the primitive, then attack the wrapper

The chain runs GF(3) linear recurrence → core-dump RWX + immediates →
logic-analyser generator matrix → unbalanced Feistel → class group vs real
quadratic cycle → NAND bit flips → 512³ tensor over a finite field.

- Recurring shape: **recover a linear structure from known-plaintext or
  redundant frames, then eliminate.** Before brute force, ask what is
  key-independent — a stage proved a checksum could not depend on the key from
  byte-identical frames alone.
- **Beware library choices.** `galois` GF(2^k) routines hang at 121-cell
  scale; plain `int64` numpy Gaussian elimination mod 3 is milliseconds.
  Off-the-shelf CP-decomposition is meaningless over a finite field — use
  Jennrich with a Krylov minimal polynomial.
- **Deliberate poisoning is part of the work**: 9% of index pairs are poisoned,
  repaired by a translation gauge plus majority vote. Do not treat outliers as
  noise to discard; treat them as the thing to vote against.

### Steganography — you are writing your own parser from stage 33 on

| Stage | Real channel |
|---|---|
| 31 driftwood | alpha-plane LSB, **column-major** |
| 32 safelight | print/negative residual, magnitude-1 class |
| 33 moire | halftone cell arrangement, **serpentine** read |
| 34 undertone | DSSS spread spectrum, **below the noise floor** |
| 35 pentimento | GIF local colour table pair order |
| 36 winnow | chaffing and winnowing |
| 37 mordant | PNG scanline **filter bytes** + the six shares |
| 38 quietus | DEFLATE literal-vs-match choice |

**Re-encoding destroys stages 35, 37 and 38 — any re-save, even lossless.**
Stage 33 is the exception: its plate is 1-bit, so a lossless re-save or even a
JPEG q40 round-trip is pixel-identical, but **anything that moves the pixel
grid kills it** — a 1-pixel shift leaves 10.3% of carrier cells legal, a 2x
down-and-up 2.2%, a 4x box downscale 1.8%. Know which category a file is in
before a tool touches and resaves it. **Work on copies.**

### Boot2Root

One method across all four boxes: **the target's own documents are the
wordlist, and its posted password policy is the hashcat rule.** One number
lifted from a personnel record is worth a hundred times the GPU time. Read the
box's documents before running a generic wordlist. Later boxes are *watched*,
not read — 29-stillwater changes on its own schedule.

## 6. Anti-patterns that cost this board specifically

- **Trusting the container check alone on stage 37.** That stage ships a
  CRC-correct entry with a homoglyph flag, precisely because the container check
  is the rule you will have trusted for six stages. Container *and* prefix, on
  every entry, every time.
- **Submitting a flag you have not eliminated.** On a credibility-scored event a
  hallucinated submission is penalised harder than an ordinary wrong guess and
  can act as a multiplier across every point you have earned.
- **Trusting `zsteg -a`, `strings`, `exiftool` or `binwalk` as an answer.**
  They are channel-finders. Past stage 32 their output is a decoy by design.
- **Assuming a clean decode means a correct answer.** Stage 16 is a correct
  DTMF decode of the wrong boot.
- **Re-solving a stage you already solved.** Check the team ledger first — a
  previous session was told a flag was unsolved when the ledger already held it.
- **Resaving an image to "look at it".** Kills three stages outright.
- **Spraying agents or requests at the platform.** Cumulative volume tripped
  HTTP 420 "Security Check" and briefly blocked both reading and submitting.
  Back off; one request at a time; challenge hosts rate-limit near 1 req/3s.
- **Assuming the event end time.** Read it from the platform API. An assumed end
  was wrong by five minutes and cost a fully-solved 3000-point challenge.

## 7. Ten minutes before the event

1. `python3 ~/.dsh/.agent-presets/ctf-operator/tools/ctfpreflight.py` — confirm
   38/38 CLI tools and 26/26 Python modules, **and the write-up pipeline row**
   (`node`/`pdfinfo`/`pdfimages` plus a reachable CDP browser on `:9222` — the
   report is a scored deliverable and cannot be rendered without it; the command
   to start the browser is printed when it is missing). Everything needed
   (tshark, hashcat,
   rizin, ghidra, steghide, stegseek, sleuthkit, photorec, pngcheck, upx) runs
   from `~/.local/bin` with no system install; if something is missing, `bash
   ~/.ctf/fetch-pkg.sh <pkg>` closes it without root.
   Then `~/.ctf/venv/bin/python
   ~/.dsh/.agent-presets/ctf-operator/tools/ctfrehearsal.py`, which runs
   `drill_nullorigin_board` (the two conventions against synthetic fixtures:
   container round-trip, CRC rejection of a flipped byte, the homoglyph audit,
   the key schedule round-trip, wrong-key garbage, six-share completeness) and
   `drill_nullorigin_workflow` (the whole finals pipeline end to end: sweep a
   synthetic board, harvest the six shares in stage order, refuse the poisoned
   seventh share, clear every real flag and convict the trap). Thirteen checks;
   exit code 0 when they pass. A failing one is a gap in the skill, not in you.
2. **Sweep the downloaded board the moment it is on disk**
   (`ctfnulltriage.py --scan`, above). It costs seconds and it is the only step
   that can hand you the six mordant shares before you have solved stage 31.
3. Load `ctf-rules-check` and confirm the event's AI policy **and** its
   credibility/hallucination clause. They differ between events and near-identical
   wording appears in documents from different organisers.
4. Read the event end time from the platform API and write it down in local time.
5. Confirm the ledger path (`~/Work/ctf/NOTES.md` for this team) and that it is
   the one being appended to.
6. Decide the split: one person per chain, one ledger, one submitter — so a
   decoy cannot be submitted by someone who did not do the elimination. Point
   `ctfnulltriage.py` at the ledger and at the downloaded artifacts before the
   first submission, so that gate is mechanical and the submitter never judges a
   candidate by eye.

## 8. The Grand Finale — a different event on the same brand

Everything above describes the **qualifier**: one linear chain with keys carried
forward. The **Grand Finale** is a different format, and this playbook does not
transfer to it.

| | Qualifier | Grand Finale (2026) |
|---|---|---|
| Shape | one linear chain, keys carried forward | **42 independent cards**, any order |
| Scoring | static | **dynamic** — value decays as teams solve |
| Budget | account lockouts | **15 attempts per card**, then terminal |
| Hints | free | **paid**, deducted from your score |
| Deliverable | — | **one PDF write-up per team**, after the close |

Verified outcome on that board: **40 of 42 closed, 16,850 points, 2nd place** —
more cards than the winners, who took more value per card. The two we could not
take: *Out of Context* (web 250 — the leaked QA credentials give an **auditor**
session, but the only template-render sink is gated server-side on the *Document
Specialist* role: anonymous → 401, auditor → 403, and the signed Flask cookie
carries no role field) and *Ghost Signal* (osint 300, zero solves board-wide).

**What the finale is actually made of.** Each category has a signature:

- **Stego / rev / crypto — the register family dominates.** Most cards are a
  16-row register of near-identical flags plus one documented integer. Load
  `ctf-register-family`. The K7/Bureau stamps (`4b37ef0f`, `5e1a73c4`,
  `0710eeee` + stage) recur across four separate waves, and the selector —
  *documented integer `mod 16`, 0-based, in the artefact's own file order* — was
  the single biggest time-saver on the board.
- **Forensics — genuine recovery, and real decoys.** The answer is in the data,
  not in tool output: a token spliced into one of 16,384 RF64 records, or a
  16-row register sitting in a PDF's incremental-update history.
- **Pwn — registers plus a documented seal.** A 4-byte `ticket-*.seal` is the
  selector input. The intended bugs are real (an arbitrary 8-byte read, an FSOP
  chain, a ptrace-widened TOCTOU) but the *flag* is still a row selection.
- **Web — one sharp wall per card.** The trap is a parameter or a role that the
  page's own JavaScript never sends.
- **Boot2Root — read the image, never download it.** The zip stores its big
  member `STORED`, so HTTP Range against the central directory gives random
  access to the guest filesystem. Both flags came out of shipped code without
  ever holding the 2.1 GB image.

**Three finale-specific traps.**

1. **A decoy parameter.** A measurement oracle indexed on `probe` while the
   page's own JS posted `bit`; every sample was noise and the card looked
   unsolvable as deployed. When measurements look like a fair coin, suspect the
   input *name* before the mechanism.
2. **The "step below the withdrawn row" reading.** A published sentence pushed
   it, and the row it selected was **refused by the platform on two separate
   cards**. The plain mod-16 landing is the rule; the step is the decoy.
3. **Not capturing the accepted string.** Five of the forty accepted values were
   never recorded, because submissions went through a browser rather than
   `ctfsub.py`. The solves were real and credited; the evidence was gone, and
   the write-up had to say so on those entries. Route every submission through
   the ledger client.

**Before the finale starts**, also read `ctf-finals-ops` (value decay, hint
economics, terminal attempt locks, cross-account budget) and
`ctf-writeup-production` (the report is due after the close, and its proof
images must be captured while the board is still live).

## Reference

The official author writeups — intended mechanism, the actual break, and the
decoys, per stage — are at
`github.com/White0xdi3/NullOrigin-CTF-2026-Writeups`; the challenge files are
GitHub Releases in `github.com/White0xdi3/NullOrigin-CTF-2026`. Read the stage
page *after* solving, not before: the writeups name the decoys, and knowing
which answer is a trap without doing the elimination trades a real skill for a
lookup table.

**Reference solvers exist for two categories only — crypto 06–13 and stego
31–38.** Forensics, reversing and boot2root ship none, deliberately. Do not plan
around a solver that is not there, and note the two different argument
conventions: the crypto solvers take the stage directory alone, while the stego
solvers take the directory and, from 32 on, the previous stage's flag.

Each category README states that category's shared mechanics once, up front —
`stego/README.md` is where the works-entry container, the key schedule, the six
mordant shares, the three decoy families and the re-encoding rules are written
down. That is the one file worth reading *before* a stage if you read any of
them.

The stego solvers chain by command line. 31 is unkeyed; 32–36 and 38 each take
the previous stage's flag; **every one of 31–36 also prints its stage's 8-byte
share — capture it, it is the only place it appears:**

```sh
# crypto 06-13: the stage directory alone, no previous flag
python3 06-bindery/solve/solve.py    /path/to/downloaded/06-bindery

# stego 31: unkeyed; 32-38: the previous flag as well
python3 31-driftwood/solve/solve.py  /path/to/downloaded/31-driftwood
python3 32-safelight/solve/solve.py  /path/to/downloaded/32-safelight  "Null0rigin{...31...}"
#   ... 33 through 36 the same way, feeding each output into the next command
python3 37-mordant/solve/solve.py    /path/to/downloaded/37-mordant \
    "Null0rigin{...36...}" <share31> <share32> <share33> <share34> <share35> <share36>
```

Treat those solvers as the reference implementation of the *format*, not as a
crutch: on a finals board the same author will keep the container and the key
schedule and change the channel, so what ports is the parsing, not the script.
