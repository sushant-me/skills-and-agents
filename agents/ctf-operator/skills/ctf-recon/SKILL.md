---
name: ctf-recon
description: Use for reconnaissance and infrastructure-tracing challenges in a CTF — DNS enumeration, WHOIS and registration history, subdomain and certificate-transparency discovery, IP/ASN attribution, historical snapshots, and pivoting from an artefact to the infrastructure or person behind it. Also covers scope discipline for third-party hosts.
---

# Recon and infrastructure tracing

These challenges give you one small artefact — a domain, an IP, a certificate, a
screenshot, a phone number — and ask you to map what sits behind it. The work is
mostly enumeration plus corroboration, not exploitation.

## Scope discipline comes first

Recon reaches **third-party infrastructure**: registrars, CDNs, hosting
providers, and often innocent bystanders (a shared IP, a reseller's other
customers, a person's unrelated social accounts).

- Stay **passive** unless the challenge explicitly asks you to touch a host:
  registries, certificate transparency, archived snapshots, public DNS.
- **Never** port-scan, fuzz, or brute-force a host that is not part of the
  challenge. An IP resolved from a challenge domain is *someone's* server, and
  it is usually not the challenge author's.
- Touching a third party that a challenge merely *references* is how a CTF
  becomes an incident. Enumerate from public records; stop at the artefact.

## No `dig` on this box — use dnspython

This machine has no `dig`, `host`, or `nslookup`. Record types and reverse
lookups go through the venv instead:

```python
~/.ctf/venv/bin/python - <<'PY'
import dns.resolver
from dns import reversename
for rt in ("A", "AAAA", "MX", "TXT", "NS", "SOA", "CNAME"):
    try:
        for r in dns.resolver.resolve("target.example", rt, lifetime=8):
            print(rt, str(r).strip('"')[:90])
    except Exception as e:
        print(rt, "--", type(e).__name__)
print("PTR", dns.resolver.resolve(reversename.from_address("1.2.3.4"), "PTR", lifetime=8)[0])
PY
```

`TXT` is where the goodies hide: SPF `include:` chains reveal the real mail
provider, verification records name the SaaS stack, and a stray TXT is
occasionally the flag itself. An `NXDOMAIN` versus a `NoAnswer` distinction
tells you whether a name exists at all — that alone maps a hidden network.

## Registration and history

```bash
whois target.example | head -40            # registrar, dates, nameservers
```

Then pivot on **each field**, not just the domain:

- **Registrar + creation date** — look the same registrant up across other
  domains registered that day; throwaway CTF infrastructure is often registered
  in a batch.
- **Nameservers** — a shared NS pair links domains that share an owner even
  when nothing else does. This is the single most reliable pivot.
- **Registrant email or org** — search it; it usually appears in other
  registrations.
- **Historical WHOIS** is often more revealing than current WHOIS, because
  privacy protection gets *added* later. Look for a period with real data.

## Subdomains and certificates

Certificate transparency is the strongest passive source: every issued
certificate is public and names the hostnames it covers.

```bash
curl -s "https://crt.sh/?q=%25.target.example&output=json" | jq -r '.[].name_value' | sort -u
subfinder -d target.example -silent
amass enum -passive -d target.example
dnsx -d target.example -silent -a -resp       # which names actually resolve
```

Then **resolve them all and group by IP**. Hosts sharing an IP are one service;
a single host with its own IP is usually the interesting one. Look for
`dev-`, `staging-`, `internal-`, `admin-`, `vpn-` — the challenge's "hidden
network" is usually a name that was never linked from anywhere.

## Attribution and mapping

```bash
curl -s "https://ipinfo.io/1.2.3.4/json"      # ASN, org, country
curl -s "https://bgpview.io/api/ip/1.2.3.4"   # prefix + peers
```

- **ASN / org** tells you the host — Cloudflare, a VPS reseller, a university.
  A university range usually means the challenge is pointing at a person, not a
  business.
- **Reverse IP** (other domains on the same address) exposes sibling
  infrastructure — often the *other* half of a challenge.
- **Historical DNS** (SecurityTrails, ViewDNS archives) shows where a domain
  pointed *before* it moved behind a CDN; that old A record is frequently the
  origin you actually want.

## Fingerprinting quietly

```bash
curl -sI https://target.example                 # Server, X-Powered-By, headers
whatweb -a 1 https://target.example
curl -s https://target.example/robots.txt https://target.example/sitemap.xml
curl -s https://target.example/.well-known/security.txt
```

A single `-I` beats a scan. Headers, `robots.txt`, and a `security.txt` give
away stack and intent without sending a single aggressive request.

## Artefact → infrastructure → person

This is the shape of most "who is behind this" challenges, and of a PERSON OF
INTEREST meta:

1. **Artefact** — a photo, a domain, a handle, a phone number, a certificate.
2. **Extract every identifier** it carries: EXIF GPS and timestamps, an email,
   a name, a username, a CDN hostname, an account id.
3. **Pivot one identifier at a time** and keep a table of candidate ↔ evidence.
   Usernames are the highest-yield pivot: the same handle is usually reused.
4. **Corroborate with something the source cannot fake** — a physical
   alignment, a matching timestamp, a mutual tag. One source is a guess; two
   independent ones are a fact.
5. **Read the flag grammar as a schema** and fill each slot from the evidence.

```bash
exiftool -a -G1 artefact.jpg            # all metadata groups
exiftool -GPSPosition -DateTimeOriginal artefact.jpg
~/.ctf/venv/bin/python -c "import phonenumbers as p; n=p.parse('+977...',None); print(p.region_code_for_number(n), p.is_valid_number(n))"
```

## Recording what you find

Recon produces a *graph*, not a flag. Keep it as one:

```
identifier  ->  what it resolves to  ->  how you know  ->  confidence
ns1.example ->  ns1.other.tld        ->  shared NS pair ->  high
1.2.3.4     ->  AS14061 DigitalOcean ->  ipinfo         ->  high
```

The "how you know" column is what lets you defend a coordinate or a name in a
writeup, and it is what stops you chasing a coincidence twice.

## Discipline

- **Corroborate before committing.** Two independent sources, or state that you
  have one.
- **Note negative results.** "crt.sh shows no subdomains" is a finding; without
  writing it down you will re-query it in an hour.
- **Archive what you find.** CTF infrastructure disappears after the event.
  Save the WHOIS, the DNS answers, and the certificate listing.
- **Timebox a dead end.** If three pivots return nothing, the artefact is
  probably not the entry point — re-read the challenge text for the one clue
  you skipped.
