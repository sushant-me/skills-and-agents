---
name: ctf-writeup-production
description: Use when a CTF requires a written report as a deliverable — a final-round write-up PDF, a submission document, or a post-event report — and whenever a markdown draft must be turned into a styled PDF with proof images. Covers the bundled markdown-to-PDF pipeline (md2html.py, print.mjs, mkpdf.sh, shot.mjs), how to capture proof screenshots from a headless browser, the structure a judge can verify, and the content rules that make a report read as the team's own work.
---

# Producing the write-up

Many final rounds score a **report**, submitted by a deadline after the board
closes, judged partly by people who never watched the event. The report is a
deliverable like any other: it has a format, a deadline, and failure modes.

Build the tooling **before** the deadline. Reconstructing evidence you did not
capture is impossible.

## 1. The bundled pipeline

`tools/writeup-pipeline/` turns a markdown source into a styled A4 PDF:

```bash
P="$DSH_HOME/.agent-presets/ctf-operator/tools/writeup-pipeline"
"$P/mkpdf.sh" report.md report.pdf
```

| File | Role |
|---|---|
| `md2html.py` | markdown → themed HTML (headings, tables, blockquotes, fenced code, `**bold**`, `*italic*`, `` `code` ``, `![alt](img)`) |
| `print.mjs` | HTML → PDF over CDP (Chrome DevTools Protocol) |
| `mkpdf.sh` | runs the two above; prints page count, page size, file size |
| `shot.mjs` | renders an HTML file and screenshots it to PNG — for proof images |

Requirements: `python3`, `node`, `pdfinfo`, and a headless Chromium started with
`--remote-debugging-port=9222`. Check it before you need it:

```bash
curl -s -m 3 http://127.0.0.1:9222/json/version >/dev/null && echo UP || \
  nohup chromium --headless=new --remote-debugging-port=9222 \
        --user-data-dir="$HOME/.ctf-profile" >/tmp/chrome.log 2>&1 &
```

`mkpdf.sh` writes the intermediate `.html` beside the output PDF. That HTML is
useful on its own — it is the thing reviewers can open without a PDF reader.

## 2. Capture proof images while the event is live

Proof is the part you cannot fake later and cannot recover afterwards.

- **Standings / final classification** — screenshot the live board *before* it
  is taken down. This is the single strongest artefact in a report and it is
  gone the moment the site closes.
- **Success responses** — the platform's own `{"correct":true,...}` reply for
  your highest-value cards.
- **Derivation output** — the terminal output of the solver script.

Write a tiny HTML wrapper that renders the text/log you want as proof, then
screenshot it:

```bash
# 1. build proof.html containing the quoted evidence (styled <pre> works well)
# 2. render it
node "$P/shot.mjs" proof.html proof.png 1100 700
```

Keep every proof file in `proof/` with a name that says what it shows
(`final-standings.png`, `proof-01-register-sweep.png`). Reference them from the
markdown with `![alt](proof/name.png)`.

## 3. Structure a judge can verify

1. **Front matter** — event, date, team name, platform accounts, final score,
   final classification. One screen, all facts.
2. **Master solve table** — one row per card: number, name, category,
   difficulty, points, solving account, accepted flag. This is the artefact a
   judge cross-checks against the platform; make it exact.
3. **A note on any value you could not confirm.** One sentence, never hidden.
4. **Per-category sections** — for each card: what it asked, the method, the
   derivation, and evidence paths.
5. **Appendices** — the technique families, the platform mechanics worth
   recording, and any correction you had to make.

Every claim points at a file. A reviewer verifying your work should never have
to guess where a number came from.

## 4. Content rules

- **Write in the team's own voice.** First person, the actual account names,
  the real order things happened in. Do not sand it into a neutral register —
  the texture is evidence that people did the work.
- **Say what you did not do.** "We could not obtain the Document Specialist
  role" is a stronger sentence than an implied success, and it is
  unfalsifiable-but-honest rather than falsifiable-and-wrong.
- **Never invent certainty.** If the accepted string was not captured, write
  *"the accepted value was not recorded in our log"* and move on. A stated gap
  is credible; a confident invention a judge can check is not.
- **Do not claim a derivation you did not perform.** If a row was reached by
  elimination against an attempt budget, call it elimination. On a
  credibility-scored board the honest label costs nothing.
- **Quote flags verbatim** from the platform, wrappers included. Authors mix
  `NullOrigin{}`, `Null0rigin{}`, `NullOriginCTF{}`, `N0{}` and zero-versus-
  letter-O deliberately; normalising them makes the table disagree with the
  platform.
- **Do not add AI attribution, and do not add filler** — no "in conclusion", no
  restating each section, no transitions that exist only to smooth the prose.

## 5. Verify the PDF before you submit

```bash
pdftotext -layout report.pdf out.txt
grep -c '\[cite' out.txt                 # 0 — no assistant citation markers
grep -ciE '\bai\b|chatgpt|claude|language model' out.txt   # 0
grep -nE '\*\*' out.txt                  # only maths like 2**33, never prose
grep -c 'Flag:' out.txt                  # one per card, none empty
pdfinfo report.pdf | grep -E 'Pages|Page size'
pdfimages -list report.pdf               # every proof image, with real dimensions
```

The `**` check matters: a bold span that straddles a source line renders as
literal asterisks, which reads as unfinished markdown.

The `pdfimages` check is the one that catches a silent proof failure. Each image
must appear at its true pixel size — a `1 x 1` entry, or a proof you know you
embedded being absent, means the path did not resolve and the page has a broken
image box where your evidence should be. Image paths are resolved relative to
the **output PDF's directory** (the intermediate `.html` is written beside it),
so `![alt](proof/x.png)` works from any working directory as long as `proof/`
sits next to the PDF.

## 6. Common failures

- Building the report after the deadline-hour scramble, with no evidence
  captured during the event.
- A master table whose flags disagree with the per-card sections.
- Attribute/provenance claims the arithmetic does not support — e.g. blaming a
  score gap on "dynamic scoring" when the difference is exactly a hint purchase.
- Proof images that show nothing verifiable (a blank terminal, a truncated
  screenshot).
- Submitting the markdown instead of the PDF.
