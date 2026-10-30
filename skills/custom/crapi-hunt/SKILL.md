---
name: crapi-hunt
description: Complete methodology for OWASP crAPI (Completely Ridiculous API) — BOLA/IDOR, broken auth, JWT, mass assignment, NoSQL injection, SSRF, improper asset management, OTP abuse, and the 2023 API Top 10. Use when the target is crAPI (localhost:8888) or any REST/API target.
source_repo: custom
source_path: ''
source_license: original
---
# OWASP crAPI (Completely Ridiculous API)

Setup: `curl -o docker-compose.yml https://raw.githubusercontent.com/OWASP/crAPI/main/deploy/docker/docker-compose.yml && docker-compose up -d` → http://localhost:8888 (web) / :8888 (api).

## Vulnerability playbook (maps to OWASP API Top 10)
- **BOLA/IDOR** — `/workshop/api/shop/orders/{id}`, `/workshop/api/mechanic/...`, `/identity/api/v2/vehicle/{id}/location` — change ids with another user's token.
- **Broken Auth** — login with `admin@example.com` / default; JWT (check `alg:none`, weak secret, no expiry); OTP/2FA bypass.
- **Mass Assignment** — `POST /identity/api/v2/user/...` with extra fields (`role`, `balance`).
- **NoSQL injection** — login `{"email":{"$ne":""},"password":{"$ne":""}}`.
- **SSRF** — the mechanic/contact-mechanic image URL, or `/workshop/api/shop/products` webhook.
- **Improper Asset Management** — old API versions (`/v1`, `/v2`), `/community/api/v2/...`; enumerate with swagger.
- **Unrestricted Resource Consumption** — OTP/verify endpoint (brute force), coupon abuse.
- **Video/Image upload** — path traversal / content-type.
- **Forgot password** — OTP in response, weak reset.

## Recon
Swagger/OpenAPI: `http://localhost:8888/swagger` or `/openapi.json`; enumerate endpoints; test each with two accounts.

Tools: `nuclei`, `sqlmap`, `ffuf`, `arjun`, Burp, `jwt_tool`.
Report each as a finding with request/response evidence.
