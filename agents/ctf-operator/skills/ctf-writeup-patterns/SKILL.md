---
name: ctf-writeup-patterns
description: Use when working a CTF challenge and you want the recurring technique patterns distilled from 30 real writeups — especially when a challenge looks unfamiliar, when the obvious interpretation feels like a trap, or when you need to know what class of bug a setup usually hides. A technique index with sources, not a solution archive.
---

# Technique patterns from real writeups

Distilled from the 30 writeups on the CTFtime new-writeups feed on 2026-09-17
(all by **Abdelkader**, published at `cybersecurityelite.com`), spanning
scriptCTF 2026, UIUCTF 2026, KaliTeam CTF 2026 and STARPWN CTF 2026.

**This is an index of transferable technique, with links. It is not those
writeups and does not reproduce them.** For any entry, read the source — it has
the full solve and the numbers.

## The single most repeated lesson

Four of the six event sets converge on the same sentence, in different words:

> **The thing the validator checks is not the thing that runs.**

| Challenge | Checked | Actually executed |
|---|---|---|
| `jail` (Java) | UTF-8 bytes | compiled bytecode — comments exist in one, not the other |
| `smaller-jail` | UTF-8 bytes | compiled bytecode — Unicode escapes and ignorable code points |
| `emacsjail2` | emitted machine code | the whole compile pipeline — compiler macros run |
| `vector-cache` | ordinary control flow | a **SIGILL handler** dispatched by `ud2` |
| `GODMODE//999` | a checksum that looks standard | a **custom** SHA-256 variant (`hashlib` is silently wrong) |
| `glyphs` | a legible interpreter | a **lambda-calculus term graph** it builds |
| `Firefly` | chunk is *serially* valid | VM assumes register-type invariants the loader never enforced |
| `Sparxie` | a BLAKE2s seal over 36 bytes | the 16-byte route is **outside** the sealed range |

**Actionable rule:** before reversing logic, ask *which representation is being
validated, and which one is being executed?* If they differ, the gap is the bug.
Corollary: when a disassembler shows intentional garbage, suspect a signal
handler or a dispatch table, not obfuscation to grind through.

## Crypto

- **"Name the primitive first."** Custom operators in a CTF are almost never new
  mathematics. `my_prod` was **RSK/Schensted**; a polynomial with distinctive
  coefficients was **Chebyshev T8**; a glyph set was **Elder Futhark** by Unicode
  block. Recognising the named object converts the challenge into "apply the
  standard result."
- **Attack the wrapper, not the primitive.** A "matrix Diffie–Hellman" was a
  **monoid** — and monoids have quotients groups do not. A "CKKS-protected
  secret" was broken by a **sign oracle on a malleable ciphertext**, not by
  breaking FHE. The advertised hardness was never the actual hardness.
- **Public data + malleability = adaptive oracle.** Whenever a scheme lets you
  transform an existing ciphertext (RSA blinding, ElGamal multiplicativity,
  CKKS addition/doubling), a one-bit-leaking output becomes a full adaptive
  search. Estimate leakage per query, then multiply.
- **Count before you theorise.** Counting distinct ciphertext values turned a
  "public-key" challenge into a 256-entry lookup table: 33 blocks, 21 distinct
  values, max alphabet 2⁸. Repetition in a ciphertext rules out IV/nonce/
  chaining and announces a deterministic substitution.
- **Check for collisions before trusting a lookup table.** All 256 subset sums
  happened to be distinct for that key — *not* a general property of 8-element
  knapsacks. A collision means ambiguous decryption.
- **Re-encryption is the gold-standard verification.** Encrypt your recovered
  plaintext and compare byte-for-byte with the original ciphertext. This catches
  a whole class of "plausible but complementary" errors.
- **Known plaintext validates the decoder before you decode the unknown.** The
  `scriptCTF` prefix pinned both a 24-letter Bacon table and a 4-constant
  formula with zero ambiguity.
- **Question the mapping, not the input.** Bacon's cipher is **24 letters**, not
  26. Brainfuck arithmetic is **mod 256**, not two's-complement. When the obvious
  mapping yields near-nonsense, the mapping is wrong.
- **Preserve the invariants the server needs.** An exploit whose plumbing steals
  protocol resources the server requires for its own side looks like a crash.

*Sources:* `uiuctf-2026-crypto-writeup`, `kaliteam-ctf-2026-crypto-writeup`,
`scriptctf-2026-writeup`.

## Web

- **Client-controlled values used as authorization — the root cause of both.**
  One challenge treated *the absence of `-L` redirect-following* (a property of
  the **client**) as a gate; another keyed the response on **User-Agent**.
  Neither is enforceable server-side.
- **`header()` in PHP is not access control.** It queues a response header and
  execution continues on the next line. A `302` **already has its body on the
  wire** — any client that reads the body (`curl`, Repeater, `fetch` with
  `redirect:'manual'`) sees the protected content before "obeying" the redirect.
  If the data is secret it must not be computed or transmitted at all.
- **`robots.txt` is public metadata.** Using it to hide or conditionally reveal
  secrets is a category error.
- **A `@deprecated` comment is a documentation edit, not a runtime removal.**
  If the server still reads the property, deprecated means shipped.
- **Production source maps leak your whole client type system** — original
  TypeScript, action IDs, deprecated properties, comments. Check for `.js.map`.
- **SSRF that steals a credential is a different bug class than SSRF that fetches
  a URL.** URL-fetch SSRF is bounded by what the endpoint can see;
  credential-leak SSRF is bounded by what the credential can do, anywhere.
- **Path globs in Vault/OpenBao ACLs are almost always wrong.** `+` matches one
  segment, `*` matches many; neither should be the primary authorization
  decision. Enumerate paths.
- **The trust boundary is not the network boundary.** Same-private-network did
  not make "wherever the address says" inside the boundary.

*Sources:* `kaliteam-ctf-2026-web-writeup`, `uiuctf-2026-web-nabi-ai-writeup`.

## Pwn

- **Payload arithmetic + tag preservation = type confusion.** Any VM primitive
  computing on a value's *payload* while leaving its *tag* alone is a
  type-confusion tool. Lua 5.5 `chgivalue` is the textbook case; V8 Smi/HeapObject
  and some CPython tagged-pointer paths are analogues.
- **Compile with the shipped compiler, patch after.** Produce the bytecode with
  `luac`, then rewrite individual opcodes. One-instruction changes preserve the
  compiler's register allocation — far cheaper than hand-assembling a chunk.
- **Format string + overflow combos:** `%N$p` to leak stack and libc, then a
  classic ret2libc with `pop rdi` / `system`.
- **Alignment matters:** a bare `ret` gadget before the call fixes 16-byte stack
  alignment and turns a SIGSEGV into a shell.
- **Hardening is irrelevant to a logic flaw.** A binary with PIE + NX + Full
  RELRO + shadow stack + IBT was defeated because it seeded `rand()` from
  `time(NULL)` — a ±2s window, no memory corruption at all. **Deterministic PRNG
  seeded from a low-entropy observable value is not random**, however hardened
  the caller.
- **Partial RELRO + one arbitrary write is a stdio-lifetime primitive.**
  `fclose@GOT → fflush` keeps a file buffer alive after the parser rejects it.
- **Freed-page reuse needs only (owner, offset, length)** to be un-deduped — a
  one-line timeline bug.

*Sources:* `uiuctf-2026-pwn-writeup`, `kaliteam-ctf-2026-pwn-writeup`.

## Reverse engineering

- **Instrument the original; do not reimplement it.** Every solve in that set
  used the challenge's own primitives via GDB scripts, Unicorn emulation, or ELF
  code-cave patches. Hand-reimplementing custom crypto or MBA-wrapped ARX is
  **punished silently** — you get a wrong constant and no error.
- **Pass signals through, don't swallow them.**
  `handle SIGILL nostop noprint pass` is the whole difference between a
  debuggable VM and a stubborn crash. If a binary behaves differently under GDB
  than standalone, check for a signal handler doing dispatch.
- **Code caves are attack surface.** Zero-filled writable ELF regions can be made
  executable, and a two-instruction syscall hook exfiltrates any register state.
- **Emulate the boundary you cannot cross** — Unicorn gave access to four
  primitives behind one firmware image without reimplementing any.
- **The route and the key can be independent.** Recognising that a 104-step maze
  route did not depend on the key reduced an exponential search to an
  `O(104)` algebraic inversion. **Ask what is key-independent before brute
  forcing.**
- **A "challenge–response" VM may be computing a compile-time constant.** Check
  whether the output depends on your input at all.
- **Map the right load offset** — `PT_LOAD` at file offset `0x10000`, not `0x0`.

*Sources:* `uiuctf-2026-reverse-engineering-writeup`,
`kaliteam-ctf-2026-reverse-writeup`.

## Sandbox / misc jails

- **Classifier evasion: read the actual layer definition.** Adversarial padding
  worked because the final layer used raw weights (negative filters allowed). A
  sibling challenge used `softplus(w)`, forcing every weight positive, and
  padding became **mathematically incapable** of lowering the score.
- **When a classifier operates on bytes, your language's semantic equivalences
  are attack surface.** Java offers a rich set: string constant folding
  (`"g"+"e"+"t"`), Unicode escape translation, identifier-ignorable code points
  inside identifiers, and comments.
- **Reflection filters are visible; native primitives are not.**
  `Class.getDeclaredField` respects a sensitive-field filter;
  `Class.getDeclaredFields0` does not. Select by **type**
  (`f.getType() == SecurityManager.class`) rather than by name or index — it
  survives JDK field-ordering changes.
- **Compilation is code execution.** A compiler macro evaluated during
  native-compile bypasses a gate that only inspects emitted machine code.

*Source:* `uiuctf-2026-misc-writeup`.

## OSINT

- **The obstacle is usually access or spelling, not source.** One target sat in a
  public archive behind Cloudflare; another was defeated by **one character** in
  a spelling. Ask "how do I reach it" before "where is it".
- **A `403` is a diagnosis, not a verdict.** Read the body: a Cloudflare
  interstitial may clear in a headed browser; a UA block needs a browser UA; an
  origin error page is final. Each demands a different response.
- **Scan the bounded set; don't query the web.** Ten scoreboards and one
  newspaper corpus are enumerable. Once the target is provably inside a small
  space, direct scanning beats search roulette.
- **Verify with something the source cannot fake** — a physical alignment, an
  exact-match vs fuzzy-match contrast. Self-contained proofs beat a lucky query.
- **Don't follow a hint off a cliff.** "The internet remembers everything"
  pointed at `archive.org`, which had nothing. A hint names the *theme*, not the
  tool.

*Sources:* `kaliteam-ctf-2026-osint-writeup`,
`uiuctf-2026-osint-something-handmade-writeup`.

## RF / space-comms misc

- **Magic bytes over file names and categories.** A file named `.raw.zst` and
  tagged "RF" revealed its true format in the first byte after decompression.
- **Protocols define bounded values for a reason — examine outside the bounds.**
  A mode field documented `0–7`; the out-of-range bytes were the message.
- **Sort before you analyse.** Both MAVLink challenges punished parsers that
  processed frames in file order. Chronological sorting is not optional in pcap.
- **Self-consistent validation beats single-source trust** — a two-byte length
  prefix and an exact 2000.0 m radius each acted as built-in checksums.
- **"Misc" is often a misdirection.** A challenge in the RF category was
  MAVLink parsing and GPS trilateration; the *category* was the trap.

*Source:* `starpwn-ctf-2026-writeup-part-1`.

## Cross-cutting heuristics

1. **The first plausible interpretation is the trap — and the title usually says
   so.** "Misdirection", visually near-meaningful output, impressive-looking
   instruction counts: all engineered to consume time from anyone who does not
   verify assumptions first.
2. **Read the shape before the content.** `115 bits` is not 14 bytes, it is 23
   five-bit groups. `28 KB` of Brainfuck is not 28 KB of logic, it is 395 folded
   ops. Modular arithmetic on the artifact size eliminates whole strategy
   classes before you write code.
3. **Prefer the historical/structural reading over the modern/convenient one.**
4. **Silence is a signal.** A program that prints nothing on success and hangs
   otherwise has moved its signal to **time, memory, or side effect**. When
   success and failure are indistinguishable in output, measure something else.
5. **Rule out the rabbit hole explicitly.** Five documented negative stego
   results were the work that made the real payload visible. Write down what
   failed — that is what makes the eventual finding credible.
6. **Classification costs 30 seconds; wrong-cipher attempts cost hours.** One
   doubled-letter mismatch collapsed an entire cipher family.
7. **Verify the decoder on known plaintext before running it on the unknown.**
8. **The flag format is a check.** A deliberate "wrong" character in a decoded
   word is the challenge telling you the alphabet is off — reread the format
   before "fixing" the plaintext.

## Source pages

- `cybersecurityelite.com/ctf-writeups/uiuctf-2026-crypto-writeup/`
- `…/uiuctf-2026-web-nabi-ai-writeup/`
- `…/uiuctf-2026-pwn-writeup/`
- `…/uiuctf-2026-reverse-engineering-writeup/`
- `…/uiuctf-2026-misc-writeup/`
- `…/uiuctf-2026-osint-something-handmade-writeup/`
- `…/kaliteam-ctf-2026-crypto-writeup/` · `-pwn-` · `-reverse-` · `-web-` · `-osint-`
- `…/scriptctf-2026-writeup/`
- `…/starpwn-ctf-2026-writeup-part-1/`

Feed: `https://ctftime.org/writeups/rss/` (30 entries, lastBuild 2026-09-17
04:36 UTC; **re-checked 2026-09-18 17:11 UTC — the same 30 entries, no new
sources, so this index is current**). Re-check the feed before a new event and
append genuinely new sources rather than re-reading the same ones. **All credit
for the underlying solves to their author.** This file exists so the *patterns*
are available before the next event, not to stand in for reading the originals.
