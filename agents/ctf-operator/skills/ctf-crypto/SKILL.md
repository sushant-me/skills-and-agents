---
name: ctf-crypto
description: Use for cryptography challenges in a CTF — RSA with weak or shared parameters, classical and substitution ciphers, block-cipher mode abuse (ECB cut-and-paste, CBC bit-flipping, padding oracles), stream-cipher nonce reuse, hash length extension, and weak PRNGs. Also covers checking whether a challenge is complete before investing, and using an embedded verifier as an offline oracle.
---

# Crypto

Identify the primitive first; the attack follows from it.

## Before you invest: is the challenge complete?

Establish early whether the provided artifacts can *actually* produce the answer,
because a crypto challenge blocked by missing key material is unsolvable no
matter how good your attack is — and it looks identical to one you have not
cracked yet.

- **List what the solver needs** (key, IV, nonce, state, seed, the routine that
  loads them) and check each against the shipped files. Read the challenge's own
  loader before writing an attack: if it calls a function that ships in no
  artifact, stop and say so.
- **Watch for a chain whose stages ship unevenly.** On a real event an
  eight-stage crypto chain was gated end-to-end by one `key → state` loading
  routine that appeared in none of the distributed files. Every stage looked
  "almost solved"; none was reachable. Recognizing that in the first hour would
  have redirected the whole event.
- **Extract the verifier as an oracle, then use it to prove the state of
  play.** A binary that checks a flag usually embeds `sha256(flag)` or a
  MAC. Pull that constant out and test candidates **offline** — it costs nothing
  and converts "I could not solve it" into "I exhaustively verified that the
  supplied artifacts cannot yield it," which is a reportable finding rather than
  a failure.
- **A verifier that self-locks will burn you.** Never run the author's own
  `verify` for guesswork: many strike out after a few wrong answers and drop a
  `.strikes` file next to the binary. Copy it out, or work from the extracted
  digest.
- Say it out loud when the evidence supports it. Announcing "this stage is
  gated by an artifact we do not have" is worth more than a tenth hour of
  grinding, and it frees the team for challenges that can be finished.

```bash
# what is this?
python3 -c "import sys;d=open('chall.bin','rb').read();print(d[:64])"
openssl rsa -pubin -in key.pub -text -noout 2>/dev/null | head
```

## RSA

Given `(n, e, c)`:

| Condition | Attack |
|---|---|
| `e == 3` and `m^3 < n` | integer cube root of `c` |
| `n` shared across two keys | `gcd(n1, n2)` |
| `n` has close factors | Fermat factorisation |
| small `d` | Wiener / Boneh-Durfee |
| `e` and `phi` not coprime | `e`-th root of unity |
| many keys, one message | Hastad broadcast |

```python
# shared prime
from math import gcd
p = gcd(n1, n2); q = n1 // p
d = pow(e, -1, (p-1)*(q-1)); print(bytes.fromhex(hex(pow(c, d, n))[2:]))
```
```python
# small e, no padding
from gmpy2 import iroot
m, exact = iroot(c, e); print(exact, bytes.fromhex(hex(int(m))[2:]))
```
`RsaCtfTool.py --publickey key.pub --uncipherfile flag.enc` automates the sweep
when the structure is unclear. Try it before hand-rolling.

## Classical

Identify by index of coincidence and frequency. `CyberChef` ("Magic") is the
fastest triage. Then: `dcode.fr`, or a substitution solver.
- ROT-N / Caesar, Vigenère (Kasiski for key length), Atbash, affine, Playfair.
- **XOR**: single-byte → brute all 256 and score; repeating-key → guess length by
  Hamming distance between blocks, then solve per-column as single-byte XOR.

## Block ciphers

```python
from Crypto.Util.Padding import pad, unpad
```
- **ECB**: identical plaintext blocks → identical ciphertext. Spot it by looking
  for repeated 16-byte chunks. Then cut-and-paste: reorder blocks to forge a
  structure (e.g. `admin` from a controlled field).
- **CBC bit-flipping**: flipping bit *i* of block *n-1* flips bit *i* of the
  plaintext of block *n*.
- **Padding oracle**: if you can distinguish "bad padding" from "bad MAC", you can
  decrypt without the key — one byte at a time. `padbuster` or ~40 lines.

## Stream ciphers / PRNG

- **Nonce reuse** in CTR/OFB/GCM: `keystream = c1 ^ p1`, then `p2 = c2 ^ keystream`.
  Also breaks GCM authentication.
- **Weak PRNG**: Python `random` is Mersenne Twister — 624 consecutive outputs
  recover the state (`randcrack`). Time-seeded → brute the seed.
- **MT19937** and LCGs are recoverable from a handful of outputs.

## Hashes

- **Length extension** on `H(secret ‖ msg)` as a MAC — `hashpump`, or hand-rolled.
- Unsalted fast hashes → rainbow tables (`crackstation`) before brute force.
- `hashid`/`haiti` to name an unknown digest.

## Discipline

State the assumption you are exploiting and test it in one line before writing
the full solve. Most crypto challenges are one observation plus arithmetic.
