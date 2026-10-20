#!/usr/bin/env python3
"""Render a KCS article (Markdown) to Word and Salesforce-ready HTML.

Usage: kcs_render.py ARTICLE.md [--outdir DIR]     (default DIR = the .md's directory)
       kcs_render.py --target TITLE [--cwd DIR]    (prints the output path for a reviewed article)
       kcs_render.py --to-md SRC                  (prints SRC (.html/.docx/.md) as Markdown)
Tables are kept in .docx but become bullet lists in .html.
Writes: <stem>.docx  <stem>.html   next to (or in DIR beside) the .md.
Requires pandoc on PATH. The .md must contain the 20 KCS field headings (## ...) in order.
"""
import argparse, html, re, shutil, subprocess, sys
from pathlib import Path

FIELDS = ["Title", "URL Name", "Summary", "Validation Status", "Article Number", "Environment",
          "Question/Problem Description", "Steps to Reproduce", "Clarifying Information",
          "Error Message", "Defect Number", "Enhancement Number", "Cause", "Resolution",
          "Workaround", "Notes", "Internal Comments", "Article Category", "Keyword Phrase",
          "Admin Ticket ID"]

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
        sys.exit("kcs_render: the 20 KCS headings must appear exactly once, in order. "
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


AREAS = ["Admin/Config", "Defects", "Enhancement", "Installation", "Licensing", "Performance",
         "Programming", "Security"]
PRONOUNS = re.compile(r"\b(?:[Yy]ou|[Yy]our|[Yy]ours|[Ww]e|[Oo]ur|[Oo]urs|us)\b")
ID_LIST = re.compile(r"MLE-\d+(\s*,\s*MLE-\d+)*")


def section(md, name):
    m = re.search(r"^## %s\s*\n(.*?)(?=^## |\Z)" % re.escape(name), md, re.M | re.S)
    return m.group(1).strip() if m else ""


def url_name(title):
    t = re.sub(r"^INTERNAL\s+", "", title.strip())
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def content_issues(md):
    """SCS content checks. Returns (errors, warnings); messages start with the field name."""
    errors, warnings = [], []
    title = re.sub(r"^INTERNAL\s+", "", (title_of(md) or "").strip())
    if len(title) > 70:
        errors.append(f"Title is {len(title)} characters; the SCS maximum is 70 (target 55, "
                      "not counting an INTERNAL prefix). Trim the error text to its key phrase.")
    elif len(title) > 55:
        warnings.append(f"Title is {len(title)} characters; the SCS target is 55 (maximum 70).")
    url = section(md, "URL Name")
    if url != url_name(title_of(md) or ""):
        errors.append(f"URL Name must be the Title lowercased with hyphens "
                      f"('{url_name(title_of(md) or '')}'), without any INTERNAL prefix; found '{url}'.")
    summary = " ".join(section(md, "Summary").split())
    if len(summary) > 250:
        errors.append(f"Summary is {len(summary)} characters; the maximum here is 250 (SCS target 160). "
                      "State the symptom or question only, never the cause or resolution.")
    elif len(summary) > 160:
        warnings.append(f"Summary is {len(summary)} characters; the SCS target is 160.")
    for f in ("Defect Number", "Enhancement Number"):
        body = section(md, f)
        if body != "N/A" and not ID_LIST.fullmatch(body):
            errors.append(f"{f} must be N/A or comma-separated MLE-<number> ids; found '{body}'.")
    cat = [l.rstrip("\\ ").strip() for l in section(md, "Article Category").splitlines() if l.strip()]
    labels = [l.partition(":")[0] if ":" in l else l + " (no colon)" for l in cat]
    if labels != ["Product Group", "Area of Interest"]:
        errors.append("Article Category must be the two lines 'Product Group: MarkLogic' and "
                      f"'Area of Interest: <value or empty>'; found {cat}.")
    else:
        group, area = (l.partition(":")[2].strip() for l in cat)
        if group != "MarkLogic":
            errors.append(f"Article Category: Product Group must be MarkLogic; found '{group}'.")
        if area and area not in AREAS:
            errors.append(f"Article Category: Area of Interest must be one of {', '.join(AREAS)} "
                          f"or empty; found '{area}'.")
    for f in ("Internal Comments", "Admin Ticket ID"):
        if not section(md, f).startswith("*("):
            errors.append(f"{f} is entered manually in Salesforce; leave the placeholder "
                          "(a line starting '*(') instead of filling it in.")
    current, fenced, seen = None, False, set()
    for line in re.sub(r"\A\s*<!--.*?-->", "", md, count=1, flags=re.S).splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif fenced:
            continue
        elif line.startswith("## "):
            current = line[3:].strip()
        else:
            for w in PRONOUNS.findall(re.sub(r"`[^`]*`", "", line)):
                if (current, w.lower()) not in seen:
                    seen.add((current, w.lower()))
                    warnings.append(f"{current}: personal pronoun '{w}'; write impersonally "
                                    "in present tense (SCS style).")
    return errors, warnings


def slugify(title, limit=60):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(s) > limit:
        cut = s[:limit]
        s = cut.rsplit("-", 1)[0] if s[limit] != "-" and "-" in cut else cut
    return s.strip("-") or "article"


def title_of(md):
    m = re.search(r"^## Title\s*\n+(.+?)\s*(?=^## |\Z)", md, re.M | re.S)
    return m.group(1).splitlines()[0].strip("#*` \t") if m else None


def output_dir(cwd):
    drafts = Path(cwd) / "kcs-drafts"
    return drafts if drafts.is_dir() else Path(cwd)


def unique_stem(directory, slug):
    base, stem, n = f"kcs-{slug}", f"kcs-{slug}", 2
    while any((Path(directory) / f"{stem}{ext}").exists() for ext in (".md", ".docx", ".html")):
        stem, n = f"{base}-{n}", n + 1
    return stem


def pandoc(*args, stdin=None):
    r = subprocess.run(["pandoc", *args], capture_output=True, text=True, input=stdin)
    if r.returncode:
        sys.exit(f"kcs_render: pandoc failed: {r.stderr.strip()}")
    return r.stdout


def require_pandoc(tail="The Markdown article is complete; only the .docx/.html rendering needs pandoc."):
    if not shutil.which("pandoc"):
        sys.exit(f"kcs_render: pandoc not found on PATH (install: https://pandoc.org/installing.html). {tail}")


def import_markdown(src):
    src = Path(src)
    if not src.is_file():
        sys.exit(f"kcs_render: file not found: {src}")
    ext = src.suffix.lower()
    if ext in (".md", ".markdown"):
        return src.read_text()
    fmt = {".html": "html", ".htm": "html", ".docx": "docx"}.get(ext)
    if not fmt:
        sys.exit(f"kcs_render: unsupported file type '{ext}' (use .md, .html or .docx)")
    require_pandoc("pandoc is needed to read .html/.docx input; paste the article text or supply a .md instead.")
    return pandoc("-f", fmt, "-t", "gfm", "--wrap=none", str(src))


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
    ap.add_argument("article", type=Path, nargs="?")
    ap.add_argument("--outdir", type=Path)
    ap.add_argument("--target", metavar="TITLE",
                    help="print the output path (no extension) for an article with this title, then exit")
    ap.add_argument("--cwd", type=Path, default=None, help="directory --target resolves against (default: current)")
    ap.add_argument("--to-md", type=Path, metavar="SRC",
                    help="convert an .html/.docx/.md article to Markdown on stdout, then exit")
    a = ap.parse_args()
    if a.target is not None:
        d = output_dir(a.cwd or Path.cwd())
        print(d / unique_stem(d, slugify(a.target)))
        return
    if a.to_md:
        sys.stdout.write(import_markdown(a.to_md))
        return
    if a.article is None:
        ap.error("ARTICLE.md is required unless --target is given")
    md = a.article.read_text()
    check_headings(md)
    check_environment(md)
    errors, warnings = content_issues(md)
    for w in warnings:
        print(f"kcs_render: warning: {w}", file=sys.stderr)
    if errors:
        sys.exit("kcs_render: SCS content errors:\n  - " + "\n  - ".join(errors))
    require_pandoc()
    out =(a.outdir or a.article.parent); out.mkdir(parents=True, exist_ok=True)
    stem = a.article.stem
    pandoc("-f", "gfm", "-t", "docx", "-o", str(out / f"{stem}.docx"), str(a.article))
    banner = re.search(r"KCS ARTICLE — (.+)", md)
    kind = banner.group(1).strip() if banner else (
        "How-To (framed as Problem/Solution per template constraints)" if "-howto-" in stem
        else "How to troubleshoot" if "-troubleshoot-" in stem
        else "Problem/Solution" if "-problem-" in stem else "Article")
    body = style_html(pandoc("-f", "gfm", "-t", "html", "--wrap=none", "--no-highlight", "-", stdin=tables_to_lists(re.sub(r"\A\s*<!--.*?-->", "", md, count=1, flags=re.S))))
    doc = ('<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8" />\n<title>%s</title>\n</head>\n'
           '<body style="%s">\n<!--\nKCS ARTICLE — %s\nPaste each section below into the matching Salesforce field.\n-->\n\n%s</body>\n</html>\n'
           % (html.escape(stem), FONT, kind, body))
    (out / f"{stem}.html").write_text(doc)
    print(f"wrote {out / (stem + '.docx')}\nwrote {out / (stem + '.html')}")


if __name__ == "__main__":
    main()
