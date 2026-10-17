---
name: ctf-pwn-rev
description: Use for binary exploitation and reverse engineering challenges in a CTF — buffer overflows, ROP, format strings, shellcode, heap bugs, and reversing stripped or packed binaries including custom VMs. Covers the toolchain, mining the flag out of .rodata, extracting embedded digest oracles, and the triage order that decides which branch a challenge is.
---

# Pwn and reversing

Both start the same way. Triage first, then branch.

```bash
file ./chall && checksec --file=./chall
strings -n 6 ./chall | head -40
nm -C ./chall 2>/dev/null | head        # symbols still present?
readelf -h ./chall | grep -E 'Type|Machine'
```

`checksec` output decides the approach:

| Finding | Consequence |
|---|---|
| No canary, NX off | classic shellcode on stack |
| Canary on | leak it first, or avoid the overflow |
| NX on, no PIE | ret2plt / ret2libc with fixed addresses |
| PIE on | need a leak before any ROP |
| Full RELRO | no GOT overwrite |

## The flag is often already in the binary — look before you reverse

Before committing to deep analysis, mine the strings and the data around them.
CTF authors embed the flag, or the check that reveals it, and the success path
usually names it:

- **`strings -n 6` first, always.** Look for the flag prefix (`Null0rigin{`,
  `CTF{`…), `CORRECT`, `Wrong`, `usage:`, "not flag-shaped", and challenge names.
- **Mine `.rodata` around the verdict strings.** The authored flag is often a
  line adjacent to the success banner — or the banner *is* the flag. On a real
  event two chained reversing challenges fell to exactly this: find `CORRECT.` /
  `Wrong.`, then read the surrounding region.

  ```bash
  strings -t x ./verify | grep -i -E 'correct|wrong|flag|usage'
  # then read the bytes around that offset
  python3 -c "d=open('verify','rb').read(); print(d[0x7f200:0x7f700])"
  ```

- **A digest is an offline oracle.** Binaries commonly embed `sha256(flag)` (or a
  keyed MAC) and compare. Extract the 32-byte constant and test candidates
  **locally at full speed** — a submission spent is a submission gone. This turns
  "guess and hope" into an exhaustive check, and it is how you *prove* a chain is
  unsolvable rather than merely unsolved.
- **Never guess against the author's own `verify` binary.** Many self-lock after
  a few wrong answers, and they ship in the same directory as the challenge (a
  `.strikes` file appearing beside the binary is the giveaway — you have already
  spent attempts). Copy it to a scratch directory first, or better, work from the
  extracted digest and never run it at all.
- **Guess in the author's grammar, not English.** These flags are authored
  phrases; a flat per-word brute force misses subjects that are bigrams. Build
  candidates from the binary's own vocabulary and test multi-word tokens as
  single units (`the_capture_timestamps_were_stretched` defeats a word-by-word
  search).

## Reversing branch

1. **Is it packed?** `binwalk`, entropy plot. UPX → `upx -d`.
2. **What language?** Go/Rust leave unmistakable strings; Python → `pyinstxtractor`
   then `decompyle3`; .NET → `dnSpy`; Java → `jadx`/`cfr`.
3. **Static**: load in Ghidra (or `rizin -A`). Rename as you understand, and
   comment — the file is your memory.
4. **Dynamic**: `ltrace`/`strace`, then `gdb` with `pwndbg` or `gef`, breakpoints
   on `strcmp`/`memcmp`, and print both operands. **Compare functions are where
   the flag is**: the program tells you what it wants if you watch it compare.
5. **Custom VM / bytecode**: find the dispatcher (`switch` with many cases or a
   jump table), dump the opcode handlers, then write an emulator rather than
   reversing each opcode by hand.
6. **Z3** for constraint chains: extract the constraints, model them, solve. Do
   not brute force a 10-byte check.

## Pwn branch

Find the bug: `gdb` + cyclic pattern to get the offset.

```bash
python3 -c "from pwn import *; print(cyclic(200))" | ./chall
# then, on the crash:
python3 -c "from pwn import *; print(cyclic_find(0x6161616161616161))"
```

**Format string** — if user input reaches `printf` directly:
```
%p %p %p ...        # leak stack, find your buffer's offset
%7$s                # read the pointer at position 7
%n                  # write (with %hn for 2 bytes)
```
Find the offset to the format string itself, then write to a GOT entry or a
return address.

**ROP**
```python
from pwn import *
elf = ELF('./chall'); rop = ROP(elf)
pop_rdi = rop.find_gadget(['pop rdi','ret'])[0]
```
`ROPgadget --binary ./chall`, or `ropper`. ret2libc needs a libc leak
(`puts(puts@got)`) then `libc.symbols['system']` and `next(libc.search(b'/bin/sh'))`.
`one_gadget ./libc.so.6` often saves the chain entirely.

**Heap** — identify the allocator and version (`libc.so.6` → tcache/fastbin
behaviour changes by glibc version). The bug is usually UAF or overflow; the
exploit is usually tcache poisoning (glibc ≥2.26) or unsafe unlink on old builds.

**Shellcode** — `pwntools asm(shellcraft.sh())`, or `shell-storm` for
arch-specific stubs. Watch for bad bytes and length limits.

## Discipline

Get a **crash with a controlled instruction pointer** before writing an exploit.
Everything after that is arithmetic. If you cannot control RIP, you do not yet
understand the bug — go back to triage rather than guessing payloads.

Keep `pwntools` scripts re-runnable with `context.log_level='debug'`, and always
test locally against the exact provided libc.
