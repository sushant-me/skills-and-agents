---
name: dvga-hunt
description: Complete methodology for DVGA (Damn Vulnerable GraphQL Application) — introspection, IDOR/BOLA on nodes, injection, batching/aliasing DoS, mutations, field-level authz, stored/deferred queries. Use when the target is a GraphQL API or DVGA (localhost:5013/graphql).
source_repo: custom
source_path: ''
source_license: original
---
# DVGA (Damn Vulnerable GraphQL Application)

Setup: `docker run -d -p 5013:5013 dolevf/dvga` → http://localhost:5013/graphql.

## Techniques
- **Introspection** — `{__schema{types{name fields{name}}}}`; if disabled, try `__type`, field-suggestion probing, or `clairvoyance`/`graphql-cop`.
- **IDOR/BOLA** — query `paste(id:)` / `user(id:)` / `node(id:)` with other users' ids; check `me` vs `user(id:)`; nested objects.
- **Injection** — SQL/NoSQL in arguments (`searchPastes(filter:)`); error-based; `$where`.
- **Mutations** — create/update/delete objects for other users; mass assignment via input types; `importPaste` (SSRF) / `uploadPaste`.
- **DoS** — deeply nested queries, batching (array of queries), alias overloading, circular fragments.
- **Field-level authz** — query private fields (e.g., `password`, `role`) that the UI hides.
- **Deferred/stream directives**, **system queries** (`__schema`, `__type`).
- **Auth** — JWT in `Authorization`; check `alg:none`, weak secret, claim tampering.

Tools: `graphql-cop -t http://localhost:5013/graphql`, `clairvoyance`, `graphw00f`, `inql`, Burp.
Report each as a finding with the GraphQL query + response evidence.
