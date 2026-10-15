#!/usr/bin/env python3
"""Render a KCS article (Markdown) to Word and Salesforce-ready HTML.

Usage: kcs_render.py ARTICLE.md [--outdir DIR]     (default DIR = the .md's directory)
Tables are kept in .docx but become bullet lists in .html.
Writes: <stem>.docx  <stem>.html   next to (or in DIR beside) the .md.
Requires pandoc on PATH. The .md must contain the 18 KCS field headings (## ...) in order.
"""
import argparse, html, re, shutil, subprocess, sys
from pathlib import Path

FIELDS = ["Title", "URL Name", "Validation Status", "Summary", "Article Number", "Environment",
          "Question/Problem Description", "Steps to Reproduce", "Clarifying Information",
          "Error Message", "Defect Number", "Enhancement Number", "Cause", "Resolution",
          "Workaround", "Notes", "Keyword Phrase", "Admin Ticket ID"]

FONT = "font-family:Verdana,Geneva,sans-serif;font-size:14px;"
MONO = "font-family:'Courier New',Courier,monospace;font-size:14px;"
STYLE = {
    "code": MONO + "background-color:#dde1e5;padding:1px 4px;border-radius:3px;color:#111;",
    "pre": MONO + "background-color:#dde1e5;border:1px solid #9aa0a6;padding:10px 12px;"
                  "border-radius:3px;white-space:pre-wrap;color:#111;",
    "table": "border-collapse:collapse;" + FONT,
    "th": "border:1px solid #9aa0a6;padding:4px 8px;background-color:#eef0f2;text-align:left;" + FONT,
    "td": "border:1px solid #9aa0a6;padding:4px 8px;vertical-align:top;" + FONT,
}
for t in ("h2", "h3", "p", "li"):
    STYLE[t] = FONT


def check_headings(md):
    found = re.findall(r"^## (.+?)\s*$", md, re.M)
    if found != FIELDS:
        missing = [f for f in FIELDS if f not in found]
        sys.exit("kcs_render: the 18 KCS headings must appear exactly once, in order. "
                 f"Missing: {missing or 'none'}; found {len(found)}: {found}")


def split_row(line):
    """Split a GFM table row into cells, ignoring pipes inside backticks."""
    cells, cur, tick = [], "", False
    for ch in line.strip().strip("|"):
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            cells.append(cur.strip()); cur = ""
        else:
            cur += ch
    return cells + [cur.strip()]


def tables_to_lists(md):
    """Salesforce articles take no tables: render each row as a bullet, first column bold.
    2 columns -> '**a** – b'; 3+ -> '**a** – *Header:* b. *Header:* c.' (as in the published drafts)."""
    lines, out, i = md.split("\n"), [], 0
    while i < len(lines):
        if (lines[i].lstrip().startswith("|") and i + 1 < len(lines)
                and re.fullmatch(r"\s*\|?[\s:|-]+\|[\s:|-]*", lines[i + 1])):
            head = split_row(lines[i]); i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                c = split_row(lines[i]); i += 1
                rest = [x for x in c[1:] if x] if len(head) == 2 else \
                       ["*%s:* %s" % (h, x) for h, x in zip(head[1:], c[1:]) if x]
                rest = [x if x.endswith((".", ":", "?")) else x + "." for x in rest] if len(head) > 2 else rest
                out.append("- **%s** – %s" % (c[0], " ".join(rest)))
            out.append("")
        else:
            out.append(lines[i]); i += 1
    return "\n".join(out)


def check_environment(md):
    body = re.search(r"^## Environment\s*\n(.*?)(?=^## )", md, re.M | re.S).group(1)
    lines = [l.rstrip("\\ ").strip() for l in body.strip().splitlines()]
    labels = [l.split(":", 1)[0] for l in lines]
    if labels != ["Product", "Version", "OS", "Component"] or not all(l.split(":", 1)[1].strip() for l in lines):
        sys.exit("kcs_render: the Environment section must be exactly four non-empty lines "
                 "'Product: ...', 'Version: ...', 'OS: ...', 'Component: ...' "
                 f"(found: {lines}). Put free-form detail under Clarifying Information.")


def pandoc(*args, stdin=None):
    r = subprocess.run(["pandoc", *args], capture_output=True, text=True, input=stdin)
    if r.returncode:
        sys.exit(f"kcs_render: pandoc failed: {r.stderr.strip()}")
    return r.stdout


def style_html(fragment):
    # Protect <pre> blocks so the inline-code style is not applied inside them.
    pres = []
    def stash(m):
        pres.append('<pre style="%s">%s</pre>' % (STYLE["pre"], re.sub(r"</?code[^>]*>", "", m.group(1))))
        return "\x00%d\x00" % (len(pres) - 1)
    out = re.sub(r"<pre[^>]*>(.*?)</pre>", stash, fragment, flags=re.S)
    for tag in ("h2", "h3", "p", "li", "table", "th", "td", "code"):
        out = re.sub(r"<%s(?=[\s>])([^>]*)>" % tag,
                     lambda m, t=tag: '<%s%s style="%s">' % (t, re.sub(r'\s*style="[^"]*"', "", m.group(1)), STYLE[t]),
                     out)
    return re.sub(r"\x00(\d+)\x00", lambda m: pres[int(m.group(1))], out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("article", type=Path)
    ap.add_argument("--outdir", type=Path)
    a = ap.parse_args()
    if not shutil.which("pandoc"):
        sys.exit("kcs_render: pandoc not found on PATH (install: https://pandoc.org/installing.html). "
                 "The Markdown article is complete; only the .docx/.html rendering needs pandoc.")
    md = a.article.read_text()
    check_headings(md)
    check_environment(md)
    out = (a.outdir or a.article.parent); out.mkdir(parents=True, exist_ok=True)
    stem = a.article.stem
    pandoc("-f", "gfm", "-t", "docx", "-o", str(out / f"{stem}.docx"), str(a.article))
    banner = re.search(r"KCS ARTICLE — (.+)", md)
    kind = banner.group(1).strip() if banner else ("How-To (framed as Problem/Solution per template constraints)" if "-howto-" in stem
            else "Problem/Solution" if "-problem-" in stem else "Article")
    body = style_html(pandoc("-f", "gfm", "-t", "html", "--wrap=none", "--no-highlight", "-", stdin=tables_to_lists(re.sub(r"\A\s*<!--.*?-->", "", md, count=1, flags=re.S))))
    doc = ('<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8" />\n<title>%s</title>\n</head>\n'
           '<body style="%s">\n<!--\nKCS ARTICLE — %s\nPaste each section below into the matching Salesforce field.\n-->\n\n%s</body>\n</html>\n'
           % (html.escape(stem), FONT, kind, body))
    (out / f"{stem}.html").write_text(doc)
    print(f"wrote {out / (stem + '.docx')}\nwrote {out / (stem + '.html')}")


if __name__ == "__main__":
    main()
