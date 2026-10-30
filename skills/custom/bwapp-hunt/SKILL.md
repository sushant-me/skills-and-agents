---
name: bwapp-hunt
description: Complete methodology for bWAPP (buggy Web Application) — 100+ vulnerabilities across SQLi, XSS, LFI/RFI, command injection, XXE, SSRF, CSRF, file upload, PHP code injection, LDAP/XPath/NoSQL injection, insecure deserialization, and more. Use when the target is bWAPP (localhost/bWAPP, bee/bug) or a deliberately-vulnerable app.
source_repo: custom
source_path: ''
source_license: original
---
# bWAPP (buggy Web Application)

Setup: `docker run -d -p 80:80 raesene/bwapp` → http://localhost/bWAPP/install.php → login `bee` / `bug`.
Set security level 0 (low). 100+ bugs organized by category — work through each.

## Categories & key bugs
- **Injection** — SQLi (`sqli_1.php?id=1' OR 1=1-- -`), blind SQLi, SQLi (POST), command injection (`?command=;id`), PHP code injection, XML/XPath injection, LDAP injection, NoSQL injection, SSRF (`?url=`), XXE.
- **XSS** — reflected (`?name=<script>alert(1)</script>`), stored (blog/guestbook), DOM, XSS via HTTP headers (`User-Agent`), XSS (cookie).
- **Broken Auth / Session** — insecure login, weak session IDs, session fixation, cookie tampering, password brute force.
- **File / Directory** — LFI (`?page=../../etc/passwd`), RFI, file upload (webshell), directory traversal, unrestricted file download.
- **CSRF / SSRF / Redirect** — CSRF on password/email change, SSRF, open redirect.
- **Logic / Misc** — insecure deserialization, XXE, HTML injection, host header injection, HTTP parameter pollution, XML bomb, mail header injection.
- **Client-side** — DOM XSS, HTML5 storage, JavaScript injection.

## Workflow
For each bug: send the payload (curl with the right method/params), confirm the effect (DB dump, command output, alert, file read), and record the exact request/response. Test with the security level at 0, then try to bypass at higher levels. Report each as a finding.
