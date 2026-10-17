#!/usr/bin/env python3
"""Minimal markdown -> styled HTML for the CTF writeup (no markdown lib on this box)."""
import html, re, sys

src = open(sys.argv[1], encoding="utf-8").read()
out = []
in_code = False
in_table = False
in_list = False
bq = []


def flush_bq():
    global bq
    if bq:
        out.append("<blockquote>%s</blockquote>" % inline(" ".join(bq)))
        bq = []


def close_list():
    global in_list
    if in_list:
        out.append("</ul>")
        in_list = False


def close_table():
    global in_table
    if in_table:
        out.append("</table>")
        in_table = False


def inline(t):
    imgs = []
    def stash(m):
        imgs.append((m.group(1), m.group(2)))
        return "\x00IMG%d\x00" % (len(imgs) - 1)
    t = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", stash, t)
    t = html.escape(t, quote=False)
    codes = []
    def stash_code(m):
        codes.append(m.group(1))
        return "\x00CODE%d\x00" % (len(codes) - 1)
    t = re.sub(r"`([^`]+)`", stash_code, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", t)
    for i, c in enumerate(codes):
        t = t.replace("\x00CODE%d\x00" % i, "<code>%s</code>" % c)
    for i, (a, s) in enumerate(imgs):
        t = t.replace("\x00IMG%d\x00" % i,
                      '<img alt="%s" src="%s">' % (html.escape(a, quote=True), s))
    return t


for raw in src.split("\n"):
    line = raw.rstrip()
    if bq and not line.startswith(">"):
        flush_bq()

    if line.startswith("```"):
        flush_bq(); close_list(); close_table()
        if in_code:
            out.append("</pre>"); in_code = False
        else:
            out.append("<pre>"); in_code = True
        continue
    if in_code:
        out.append(html.escape(line, quote=False))
        continue

    if not line.strip():
        flush_bq(); close_list(); close_table()
        continue

    if re.match(r"^---+$", line.strip()):
        flush_bq(); close_list(); close_table(); out.append("<hr>"); continue

    m = re.match(r"^(#{1,4})\s+(.*)$", line)
    if m:
        flush_bq(); close_list(); close_table()
        lvl = len(m.group(1))
        out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
        continue

    if line.lstrip().startswith("|"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue  # separator row
        if not in_table:
            out.append("<table>"); in_table = True
            out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
        else:
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
        continue
    close_table()

    m = re.match(r"^\s*[-*]\s+(.*)$", line)
    if m:
        if not in_list:
            out.append("<ul>"); in_list = True
        out.append(f"<li>{inline(m.group(1))}</li>")
        continue

    m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
    if m:
        if not in_list:
            out.append("<ul>"); in_list = True
        out.append(f"<li>{inline(m.group(2))}</li>")
        continue

    close_list()
    if line.startswith(">"):
        bq.append(line.lstrip("> ").strip())
    else:
        out.append(f"<p>{inline(line)}</p>")

flush_bq(); close_list(); close_table()
if in_code:
    out.append("</pre>")

CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color:#1a1a1a;
       font-size:10.5pt; line-height:1.55; }
h1 { font-size:20pt; color:#0b2545; border-bottom:3px solid #0b2545; padding-bottom:5pt; }
h2 { font-size:14pt; color:#0b2545; margin-top:20pt; border-bottom:1px solid #cbd5e1; padding-bottom:3pt;
     page-break-after:avoid; }
h3 { font-size:11.5pt; color:#123f6d; page-break-after:avoid; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size:9pt; background:#f2f4f7;
       padding:1px 4px; border-radius:3px; }
pre { background:#1e293b; color:#e2e8f0; padding:9pt 11pt; border-radius:5px; font-size:8.5pt;
      white-space:pre-wrap; word-break:break-word; page-break-inside:avoid; }
img { max-width:100%; border:1px solid #cbd5e1; border-radius:5px; margin:6pt 0; page-break-inside:avoid; }
table { width:100%; border-collapse:collapse; margin:8pt 0; font-size:9.5pt; page-break-inside:avoid; }
th { background:#0b2545; color:#fff; text-align:left; padding:5pt 7pt; }
td { border-bottom:1px solid #dde3ea; padding:4pt 7pt; vertical-align:top; }
blockquote { background:#f7f9fc; border-left:4px solid #0b2545; margin:8pt 0; padding:6pt 10pt; }
hr { border:none; border-top:1px solid #cbd5e1; margin:14pt 0; }
ul { margin:5pt 0 5pt 16pt; }
li { margin:2pt 0; }
"""

open(sys.argv[2], "w", encoding="utf-8").write(
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    f"<style>{CSS}</style></head><body>" + "\n".join(out) + "</body></html>"
)
print("wrote", sys.argv[2])
