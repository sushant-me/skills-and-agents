---
name: ctf-register-family
description: Use when a challenge ships a REGISTER of candidate flags — several near-identical tokens sharing one prefix/stamp, often 16 of them with revision letters — and one of them is the real answer. Covers how to recognise the family on sight, the one rule that selects the in-force row (documented integer mod register size, 0-based, in the artefact's own file order), the decoy readings that look smarter and get rejected, and how to verify a row offline before spending a submission. Load it the moment you see two flags differing only in a middle segment, or a "revision index"/"candidate list"/"register" file.
---

# The register family: the answer is a *selection*, not a value

Some authors ship a challenge whose answer is not derivable from a computation
at all. Instead the release contains a **register** — a fixed set of candidate
tokens, exactly one of which is in force — plus one **documented integer**
somewhere in the prose or metadata. The whole challenge is *which row*.

Getting this wrong is expensive in a specific way: every candidate looks like a
plausible flag, so you can burn a 15-attempt budget guessing rows that the
artefact already told you how to eliminate. Getting it right converts an
"unsolvable" card into a two-minute read.

## 1. Recognise it on sight

You are in this family when **all** of these hold:

- Two or more flags differ **only** in a middle segment — e.g.
  `N0{4b37ef0f-JS3R9Q6GT91RCE6QFSSEWP3KGG}` vs
  `N0{4b37ef0f-8QMGHNAYPPQWJRF1K47NSJG53R}`: same 8-hex stamp, different tail.
- The count of them is a round number — **16** is the common one.
- They are labelled with **revision letters**, typically
  `A B C D E F G H J K L M N P R T` (an alphabet that skips `I O Q S` to avoid
  confusion with `1 0`).
- A file names them: `*-revisions.log`, `candidate-revisions.*`,
  `commission-note`, `*-register.*`, or the token list is embedded in a binary's
  `.rodata` / `.comment`.

The moment you see this, **stop trying to decrypt anything**. There is nothing
to decrypt — the release is a lookup table with a selector.

## 2. The stamp carries zero information

Do not read meaning into the shared prefix. On this family it encodes the
stage/challenge number and nothing else. Its own author documentation says so:

> the 8-hex prefix *"carries ZERO validity information"*

Any "MJD", epoch, or date reading of a stamp is a deliberately planted decoy.

The 26-character tail is **Crockford base32 of exactly 128 bits**, left-aligned:
the top two bits are always `00`, so

```python
base32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
value  = int(tail, base32)          # 130-bit integer
value & 3 == 0                      # always true for a well-formed row
```

Confirm this once and you have verified you are looking at the family and not
at 16 unrelated tokens.

## 3. THE RULE

> **`index = documented_integer mod register_size`, 0-based, in the order the
> artefact itself lists the rows. The row it lands on is the answer.**

Three things that rule out are as important as what it says:

- **0-based.** Row `A` is index 0, so `mod 16 == 5` is the sixth row, `REV F`.
- **The artefact's own file order** — not alphabetical, not the order you would
  sort them into, not the order they appear in a string dump. Read the register
  file top-to-bottom.
- **The documented integer is documented.** It is stated in prose, or written
  as a plain 4-byte big-endian value in a small `*.seal` / ticket file, or named
  as a ceremony input in a `gate-in` file. If you are choosing the integer
  yourself because it "looks meaningful", you are guessing.

```python
reg   = "A B C D E F G H J K L M N P R T".split()
row   = reg[N % 16]          # N = the documented integer
```

**Verified landings on a live board** (each accepted by the platform):

| Stage | Documented integer | `mod 16` | Row |
|---|---|---|---|
| Randomwalk | class number `n1 = 78940088` | 8 | **REV J** |
| Coda | `f = 0x162610443d1dca65` | 5 | **REV F** |
| Beatnote | unit designation `2029` | 13 | **REV P** |

In each case the integer came out of the stage's own published mechanism — a
class group, a permutation input, a unit number — and the row it selected was
the one the platform accepted.

## 4. Decoy readings — these look smarter and get rejected

The family is designed so the *sophisticated* reading is the wrong one.

- **"Take the row below the withdrawn row."** Some registers label one row
  `withdrawn`. A published sentence will push you to step to the next line.
  This is empirically refuted: the stepped-to row was submitted and **returned
  `correct:false`** on two separate stages in one event.
- **The withdrawn row itself.** Labels like `rev C`, `rev K`, `legacy`,
  `repaired`, `wrong-offset`, `withdrawn at REV P`, `(withdrawn)` exist
  *precisely* to make a wrong row look authoritative. A label is not evidence.
- **The first row / the most-printed row.** Boilerplate that appears in every
  artefact is a decoy by construction.
- **The row that appears in the most documents.** The loudest artefact is
  never the answer in this family.
- **A stamp or epoch interpreted as a date → index.** Refuted by the author's
  own README.
- **Counts of things** (record counts, page counts, frame counts) — attractive
  in powers-of-two designs because they collapse to index 0. If every design
  integer is a power of two it *cannot* discriminate; find the one documented
  integer that is not.

## 5. The generalisable principle

Underneath the arithmetic is the lesson that transfers to every challenge by
this kind of author:

> **The flag is the row the artefact itself corroborates — a published rule,
> never a preference.**

Corroboration can take other shapes when the mod-16 rule has nothing to bite
on. Real examples that decided acceptable rows:

- a **planting bijection** — 15 of 16 tokens are quoted verbatim as decoys
  elsewhere in the release, one per letter; the single letter that is *never*
  planted is the live one;
- a **certificate that prints the row outright** (`... CERTIFICATE REV L ...
  <flag>`) — the artefact that states *both* the revision and the figure is the
  live one, and anything offering only a token is a decoy;
- a **weight-window minimum** — the only published width-scale quantity is
  `weights[ALLOC[tooth]]`, and the extreme value is unique;
- the **build mark compiled into the service binary** — one row present in the
  `.comment` section and nowhere else (recoverable with
  `readelf -p .comment <binary>` or `strings`).

Test your candidate against the *artefact*, and be able to point at the bytes
that select it. If you cannot point, you are choosing, not deriving.

## 6. Verify before you spend a submission

```bash
# the tail is Crockford base32 of 128 bits?
python3 - <<'EOF'
b32="0123456789ABCDEFGHJKMNPQRSTVWXYZ"
t="<26-char tail>"
v=int(t,b32); print(hex(v), "top2==00:", v>>128==0)
EOF

# every candidate row a shipped file mentions, in file order
grep -oE 'N0\{[0-9a-f]{8}-[0-9A-Z]{26}\}' -r . | sort -u
readelf -p .comment <binary> 2>/dev/null | grep -oE 'N0\{[^}]*\}'
```

Then check the ledger. On this family the same token often appears in several
stages, and a row you already tried and were refused is a row you must not
spend again.

## 7. When derivation is impossible: elimination is legitimate

Some stages ship the register but never ship the selector (the sealing library
is missing from every release, the selector file is unlabelled). You are then
choosing among 16 rows with a server-reported attempt budget.

That is a legitimate metagame play, and it should be done **deliberately**:

- rank rows by every weak signal you have (prose order, planting, recency),
- probe the **highest-ranked** row first, not the first row,
- log every probe and its `attemptsLeft` so the team never re-tries a burned
  row,
- keep the remaining budget for the rows you can still reason about.

One stage in a real event was landed this way: a teammate had already burned 11
rows, the probe was refused, and the accepted row (`REV H`, index 7) was reached
by elimination. Record it honestly as *"reached by elimination, not derivation"*
— on a credibility-scored board that honesty costs nothing and an invented
derivation costs a great deal.

## 8. Do not let the register fool you into thinking you are done

The register selects the **flag**. It does not tell you what the challenge was
about, and it does not produce the artefact that proves it. When you land a row:

1. write the index arithmetic into the challenge notes (`N mod 16 = i -> REV X`),
2. record the **accepted string verbatim** at submission time,
3. say in the write-up which integer selected it and where that integer is
   documented.

A row you selected but cannot explain is indistinguishable, six hours later,
from a row you guessed.
