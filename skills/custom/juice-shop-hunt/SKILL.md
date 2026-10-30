---
name: juice-shop-hunt
description: Complete methodology to find ALL 116 OWASP Juice Shop challenges. Use when the target is OWASP Juice Shop (localhost:3000 or any instance) or when testing a deliberately-vulnerable training app. Covers every challenge category (Broken Auth, Broken Access Control, Security Misconfiguration, Vulnerable Components, Cryptographic Issues, Injection, XSS, Sensitive Data Exposure, Improper Input Validation, Broken Anti-Automation, Security through Obscurity, Observability, Misc) plus the 35 coding-fix challenges.
source_repo: custom
source_path: ''
source_license: original
---
# OWASP Juice Shop — find ALL 116 challenges

Juice Shop is a deliberately vulnerable app with **116 challenges** across 13 categories.
Goal: find and exploit as many as possible, with real request/response evidence.

## Step 0 — Get the ground-truth challenge list FROM THE APP
The app exposes its own challenge list. Fetch it first so you know exactly what to find:
```
curl -s http://localhost:3000/api/Challenges/ | python3 -m json.tool   # all 116 + solved flags
curl -s http://localhost:3000/api/Challenges/?name=...                 # filter
```
Track solved/unsolved by category. This is your checklist — work it top to bottom.

**Exact distribution (116 total):**
Sensitive Data Exposure 17 · Injection 14 · Improper Input Validation 12 ·
Broken Access Control 12 · XSS 9 · Vulnerable Components 9 · Broken Authentication 9 ·
Miscellaneous 6 · Security Misconfiguration 5 · Cryptographic Issues 5 ·
Observability Failures 4 · Broken Anti Automation 4 · Security through Obscurity 3 ·
Insecure Deserialization 3 · Unvalidated Redirects 2 · XXE 2.

## Step 1 — Recon the surface
```
httpx -u http://localhost:3000 -tech-detect -title -status-code
katana -u http://localhost:3000 -jc -d 3 -silent > endpoints.txt
ffuf -u http://localhost:3000/FUZZ -w wordlists/raft-medium-directories.txt -mc 200,301,302,401,403
nikto -h http://localhost:3000
nuclei -u http://localhost:3000
```
Key known surfaces: `/rest/…`, `/api/…`, `/ftp/`, `/b2b/v2/orders`, `/rest/user/login`,
`/rest/products/search`, `/rest/basket`, `/api/Users`, `/api/Feedbacks`, `/api/SecurityQuestions`,
`/rest/admin/application-configuration`, `/metrics`, `/support/logs`, `/rest/chat`.

## Step 2 — Challenge playbook by category

### Broken Authentication
- Default admin: `admin@juice-sh.op` / `admin123`
- Bjoern's password: `admin@juice-sh.op` + OSINT (favorite pet etc.); login with `'` SQLi
- Password reset via **security question** (answer is public/guessable) → reset any user
- 2FA: `POST /rest/2fa/status` leaks TOTP secret → forge TOTP
- OAuth: `POST /rest/user/login` with `"oauth": true` for `bjoern@…`; token via `/rest/user/whoami`
- GDPR data erasure / login as deleted user; reset Bender's password

### Broken Access Control (BOLA/IDOR)
- Admin section: navigate to `/#/administration` as admin (get admin via mass assignment/SQLi)
- **IDOR on basket**: `GET /rest/basket/{id}` with your token, change id → other users' baskets
- **Mass assignment**: `POST /api/Users` with `"role":"admin"` (or PUT) → self-promote
- Forge feedback: five-star `PUT /api/Feedbacks/{id}`
- View another user's basket / order; access `/rest/basket/1` etc.
- `/api/Feedbacks/` returns all feedback; `/api/Complaints/` all complaints (unauth)
- Product tampering / B2B order manipulation

### Security Misconfiguration
- Error handling: send malformed input → verbose stack traces
- Deprecated interface: `/b2b/v2/orders` still active
- XXE data access: upload XML invoice/order with external entity
- `robots.txt` → `/ftp`; `/ftp` directory listing
- Access log (`/support/logs`), `/metrics` (Prometheus), `/api-docs`, `/swagger`

### Vulnerable Components
- `/ftp/package.json.bak` (null-byte `%2500.md`) → component versions → CVEs
- Known CVEs for the bundled libs (old Angular/express versions)

### Cryptographic Issues
- Forged coupon: sign a coupon code (guess the key / use leaked key)
- JWT: `jwt.pub` / `premium.key` leaked; **RS256→HS256 confusion**; alg:none; weak secret
- Password hash in JWT payload (base64) → crack

### Injection
- **Login SQLi**: `' OR 1=1--` in email
- **Union SQLi** product search: `')) UNION SELECT ... FROM Users--`
- DB schema leak; NoSQL injection (`{"$ne":""}`) where applicable
- `POST /rest/user/login` with `{"email":"...","password":{"$ne":null}}`

### XSS
- **DOM XSS**: `/#/search?q=<iframe src="javascript:alert(document.domain)">`
- **Reflected XSS**: order tracking `/#/track-result?id=<iframe ...>`
- **Stored XSS**: product review / feedback with `<iframe src=...>`
- API-only XSS; CSP bypass; HTTP header XSS; bypass security policy (`bypassSecurityTrustHtml`)

### Sensitive Data Exposure
- Confidential document (`/ftp/…`), forgotten backup (`package.json.bak`), login Bjoern
- Access logs, `/metrics`, `/support/logs`, `/api/Challenges` (exposes all), `audit.json`
- Exposed `jwt.pub`, `premium.key`, `app-configuration`

### Improper Input Validation
- Zero stars (`POST /api/Feedbacks` rating 0), negative quantity (`PUT /api/BasketItems/{id}` qty -1)
- Poison null byte; missing encoding; list empty basket; free coupon; etc.

### Broken Anti-Automation
- CAPTCHA bypass, rate-limit bypass on login, extra language, multiple likes

### Security through Obscurity
- Honeypot (`/ftp` trap), access a hidden path, misplace a path

### Observability Failures
- Access log, `/metrics`, exposure via logs

### Miscellaneous
- Bully chatbot, kill chatbot, cross-site imaging, SSTI, video XSS, arbitrary file write,
  web3 sandbox, redirects, etc.

## Step 3 — Verify + report
For each challenge: capture the exact request + response (curl) as evidence.
Then output findings JSON `{title, vuln_class, severity, endpoint, summary, steps_to_reproduce, impact, evidence}`.
Track which of the 116 you confirmed. Push for maximum coverage — work every category.

## The 35 coding challenges
For challenges with a coding fix: identify the vulnerable source (Juice Shop is open-source —
`https://github.com/juice-shop/juice-shop`), locate the flaw (e.g., `lib/insecurity.ts`,
`routes/*.ts`, `server.ts`), and describe the fix (parameterized queries, output encoding,
authorization checks, safe deserialization).
