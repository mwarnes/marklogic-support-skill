# `/kcs-review` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/kcs-review` command that reviews a KCS article written by another engineer (md/html/docx path or pasted text), summarises recommendations, and on acceptance writes the revised article as `.md`, `.docx` and Salesforce `.html`.

**Architecture:** A new prompt template (`prompts/kcs-review.md`) drives the workflow, using a new review checklist in `kcs-writing.md`. Deterministic pieces (import of html/docx to Markdown, title-to-filename slug, output directory choice, collision suffixing) live in `kcs_render.py` as tested functions exposed through two new CLI flags, so the prompt only shells out to them. Final rendering reuses the existing `kcs_render.py` path unchanged.

**Tech Stack:** Python 3 stdlib (`unittest`/pytest), pandoc, Markdown prompt templates.

## Global Constraints

Spec: `docs/superpowers/specs/2026-10-20-kcs-review-command-design.md`.

- Output filename: `kcs-<slug>.{md,docx,html}`, slug derived from the article's Title field.
- Output directory: `./kcs-drafts/` if it exists in the current working directory, otherwise the current project folder (the working directory).
- The original article is never modified; if a target filename exists, add a numeric suffix.
- Accept is all-or-nothing: accept applies every recommendation and shows the full revised article for final confirmation; decline asks which parts need correction or improvement, revises, re-summarises.
- Findings are grouped must-fix / should-fix / optional.
- Unverifiable claims are flagged, never silently corrected.
- All 18 `## ` headings in order and the four-line Environment section are enforced by the existing `kcs_render.py` checks; do not weaken them.
- pandoc is needed only for html/docx import and for rendering; `.md`/pasted input works without it until rendering, and the `.md` is still written if pandoc is missing.
- No ticket audit-trail entries; no review-notes file unless the user asks in chat.
- Existing CLI `kcs_render.py ARTICLE.md [--outdir DIR]` must keep working unchanged.

---

## File Structure

- Modify `skills/marklogic-support/scripts/kcs_render.py` — add `slugify`, `title_of`, `output_dir`, `unique_stem`, `import_markdown`, `require_pandoc`, and CLI flags `--to-md SRC` and `--target TITLE`.
- Modify `tests/test_kcs_render.py` — tests for the above.
- Modify `skills/marklogic-support/references/kcs-writing.md` — append "Reviewing an article".
- Create `prompts/kcs-review.md` — the command template.
- Modify `README.md`, `skills/marklogic-support/SKILL.md` — pointers.

---

### Task 1: Slug, title, output-directory and collision helpers

**Files:**
- Modify: `skills/marklogic-support/scripts/kcs_render.py`
- Test: `tests/test_kcs_render.py`

**Interfaces:**
- Produces:
  - `slugify(title: str, limit: int = 60) -> str`
  - `title_of(md: str) -> str | None` (first line under `## Title`)
  - `output_dir(cwd: Path) -> Path` (`cwd/kcs-drafts` if it is a directory, else `cwd`)
  - `unique_stem(directory: Path, slug: str) -> str` (`kcs-<slug>`, or `kcs-<slug>-2`, `-3`… if any of `.md/.docx/.html` exists)
  - CLI: `kcs_render.py --target TITLE [--cwd DIR]` prints `<output_dir>/<unique_stem>` (no extension) and exits 0.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_kcs_render.py` before the `if __name__` line:

```python
class NamingTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(kcs_render.slugify("SAML: Redirect Loop (Okta) / Login!"), "saml-redirect-loop-okta-login")
        self.assertEqual(kcs_render.slugify("  ---  "), "article")

    def test_slugify_truncates_on_word_boundary(self):
        s = kcs_render.slugify("alpha " * 30)
        self.assertLessEqual(len(s), 60)
        self.assertFalse(s.endswith("-"))
        self.assertTrue(set(s.split("-")) == {"alpha"})

    def test_title_of(self):
        md = "## Title\n\nHow to renew a certificate\n\n## URL Name\n\nx\n"
        self.assertEqual(kcs_render.title_of(md), "How to renew a certificate")
        self.assertIsNone(kcs_render.title_of("## Summary\n\nx\n"))

    def test_output_dir(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(kcs_render.output_dir(d), d)
        (d / "kcs-drafts").mkdir()
        self.assertEqual(kcs_render.output_dir(d), d / "kcs-drafts")

    def test_unique_stem_suffixes_on_any_existing_format(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(kcs_render.unique_stem(d, "foo"), "kcs-foo")
        (d / "kcs-foo.docx").write_text("x")
        self.assertEqual(kcs_render.unique_stem(d, "foo"), "kcs-foo-2")
        (d / "kcs-foo-2.html").write_text("x")
        self.assertEqual(kcs_render.unique_stem(d, "foo"), "kcs-foo-3")

    def test_cli_target_prefers_kcs_drafts(self):
        d = Path(tempfile.mkdtemp()); (d / "kcs-drafts").mkdir()
        r = subprocess.run([sys.executable, str(SCRIPT), "--target", "My Title!", "--cwd", str(d)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(d / "kcs-drafts" / "kcs-my-title"))

    def test_cli_target_falls_back_to_cwd(self):
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, str(SCRIPT), "--target", "My Title!", "--cwd", str(d)],
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), str(d / "kcs-my-title"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_kcs_render.py -k NamingTest -v`
Expected: FAIL (`AttributeError: module 'kcs_render' has no attribute 'slugify'`).

- [ ] **Step 3: Implement**

In `kcs_render.py`, add after `check_environment` (before `pandoc`):

```python
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
```

Change `main()` argument parsing and add an early branch. Replace

```python
    ap.add_argument("article", type=Path)
    ap.add_argument("--outdir", type=Path)
    a = ap.parse_args()
```

with

```python
    ap.add_argument("article", type=Path, nargs="?")
    ap.add_argument("--outdir", type=Path)
    ap.add_argument("--target", metavar="TITLE",
                    help="print the output path (no extension) for an article with this title, then exit")
    ap.add_argument("--cwd", type=Path, default=None, help="directory --target resolves against (default: current)")
    a = ap.parse_args()
    if a.target:
        d = output_dir(a.cwd or Path.cwd())
        print(d / unique_stem(d, slugify(a.target)))
        return
    if a.article is None:
        ap.error("ARTICLE.md is required unless --target is given")
```

Also update the module docstring's `Usage:` line to add `kcs_render.py --target TITLE [--cwd DIR]` (prints the output path for a reviewed article).

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_kcs_render.py -v`
Expected: all PASS (pandoc-dependent tests PASS or skip), including the unchanged existing tests.

- [ ] **Step 5: Commit**

```bash
git add skills/marklogic-support/scripts/kcs_render.py tests/test_kcs_render.py
git commit -m "feat: kcs_render --target derives output path from article title

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Import html/docx/md to Markdown

**Files:**
- Modify: `skills/marklogic-support/scripts/kcs_render.py`
- Test: `tests/test_kcs_render.py`

**Interfaces:**
- Consumes: existing `pandoc(*args, stdin=None)`, `FIELDS`, `FIXTURE` in tests.
- Produces:
  - `require_pandoc() -> None` (exits with the existing "pandoc not found" message; `main()` is changed to call it)
  - `import_markdown(src: Path) -> str` — `.md`/`.markdown` read as-is; `.html`/`.htm`/`.docx` converted via `pandoc -f <html|docx> -t gfm --wrap=none`; anything else exits with a message naming the supported types.
  - CLI: `kcs_render.py --to-md SRC` prints the Markdown to stdout, exit 0.

- [ ] **Step 1: Write the failing tests**

Append before the `if __name__` line:

```python
class ImportTest(unittest.TestCase):
    def test_md_passthrough_needs_no_pandoc(self):
        self.assertEqual(kcs_render.import_markdown(FIXTURE), FIXTURE.read_text())

    def test_unsupported_extension_rejected(self):
        d = Path(tempfile.mkdtemp()); p = d / "a.pdf"; p.write_text("x")
        r = subprocess.run([sys.executable, str(SCRIPT), "--to-md", str(p)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(".docx", r.stderr)

    def test_missing_file_rejected(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--to-md", "/nonexistent/a.md"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_html_and_docx_round_trip_to_18_headings(self):
        d = Path(tempfile.mkdtemp()); self.assertEqual(run(FIXTURE, d).returncode, 0)
        for ext in (".html", ".docx"):
            md = kcs_render.import_markdown(d / (FIXTURE.stem + ext))
            self.assertEqual(re.findall(r"^## (.+?)\s*$", md, re.M), kcs_render.FIELDS, ext)

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_imported_html_can_be_rendered_again(self):
        d = Path(tempfile.mkdtemp()); self.assertEqual(run(FIXTURE, d).returncode, 0)
        r = subprocess.run([sys.executable, str(SCRIPT), "--to-md", str(d / (FIXTURE.stem + ".html"))],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        again = d / "again.md"; again.write_text(r.stdout)
        self.assertEqual(run(again, d / "out").returncode, 0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_kcs_render.py -k ImportTest -v`
Expected: FAIL (`import_markdown` not defined / unrecognised `--to-md`).

- [ ] **Step 3: Implement**

In `kcs_render.py`, add after `pandoc(...)`:

```python
def require_pandoc():
    if not shutil.which("pandoc"):
        sys.exit("kcs_render: pandoc not found on PATH (install: https://pandoc.org/installing.html). "
                 "The Markdown article is complete; only the .docx/.html rendering needs pandoc.")


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
    require_pandoc()
    return pandoc("-f", fmt, "-t", "gfm", "--wrap=none", str(src))
```

In `main()`: add the argument and branch, and replace the inline pandoc check.

```python
    ap.add_argument("--to-md", type=Path, metavar="SRC",
                    help="convert an .html/.docx/.md article to Markdown on stdout, then exit")
```

placed after `--cwd`, and after the `--target` branch add:

```python
    if a.to_md:
        sys.stdout.write(import_markdown(a.to_md))
        return
```

Replace the existing block

```python
    if not shutil.which("pandoc"):
        sys.exit("kcs_render: pandoc not found on PATH ...
                 "The Markdown article is complete; only the .docx/.html rendering needs pandoc.")
```

with `require_pandoc()`. Add `kcs_render.py --to-md SRC` to the docstring `Usage:` block.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest tests -v`
Expected: all PASS (pandoc tests PASS or skip); existing parse_dump / analyse_logs tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add skills/marklogic-support/scripts/kcs_render.py tests/test_kcs_render.py
git commit -m "feat: kcs_render --to-md imports html/docx/md articles as Markdown

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Review checklist, `/kcs-review` prompt and docs

**Files:**
- Modify: `skills/marklogic-support/references/kcs-writing.md` (append)
- Create: `prompts/kcs-review.md`
- Modify: `README.md` (after the "Writing a KCS article" section, ~line 42)
- Modify: `skills/marklogic-support/SKILL.md` (after the "## KCS articles" paragraph, ~line 89)

**Interfaces:**
- Consumes: `kcs_render.py --to-md SRC`, `--target TITLE`, and the existing `kcs_render.py ARTICLE.md` render call (Tasks 1–2); `kcs-writing.md` rules.

- [ ] **Step 1: Append the checklist to `kcs-writing.md`**

````markdown

## Reviewing an article (used by `/kcs-review`)

Review an article written by someone else against everything above, then group findings:

- **must-fix** — breaks the format or is unsafe: missing/misordered/extra headings, Environment not
  exactly the four standard lines, unsanitised customer data (names, hosts, IPs, IDs, secrets,
  ticket number outside Admin Ticket ID), unconfirmed Cause stated as fact, commands that cannot
  run as written, claims contradicted by the skill's reference files.
- **should-fix** — hurts findability or clarity: weak Title or Keyword Phrase, URL Name not
  lowercase-hyphen, wrong Problem/Solution vs How-To framing (How-To fields should be
  `N/A — ...`), `Validation Status` stronger than the evidence, scope/versions not stated
  honestly, missing "substitute these values" notes, no Management API alternative where one exists.
- **optional** — style: wording, bold/backtick conventions, table cell length, ordering of steps.

Checks that cannot be settled from the article and the references (a version number, a behaviour
claim) are reported as "could not verify" — never silently changed. An imported article whose
headings differ from the 18 fields is mapped only where the match is unambiguous (e.g. `Problem`
→ `Question/Problem Description`); otherwise the field is reported missing.
````

- [ ] **Step 2: Create `prompts/kcs-review.md`**

````markdown
---
description: Review a KCS article written by another engineer (md/html/docx or pasted) and write the revised article as Markdown, Word and Salesforce HTML
argument-hint: [path to article]
---

This is the `/kcs-review` workflow the user's own team maintains for reviewing a Knowledge-Centered Support article that another engineer sent for review (see `/kcs` in `prompts/kcs.md`, which writes articles from a ticket). It checks the article against the team's 18-field format and sanitisation rules, summarises recommendations, and on acceptance writes the revised article as Markdown, Word and Salesforce HTML. Imperative wording below is only there so steps are executed rather than narrated.

Article path argument (optional): $1

1. **Load the skill material.** Read `skills/marklogic-support/references/kcs-writing.md` (locate the skill by checking the same paths as `/ticket` step 2 — pi and Claude Code locations, `~/.claude/skills/marklogic-support/` included; if none exists or the symlink is broken, say so and stop). Set `<skill-dir>` to the directory that holds it. Use its "Reviewing an article" section as the checklist.

2. **Get the article.**
   - If `$1` is non-empty, it is the path. Otherwise ask in plain chat text: "Give me the path to the KCS article (.md, .html or .docx), or paste the article text here." Wait for the reply.
   - A path: run (shell tool) `python3 <skill-dir>/scripts/kcs_render.py --to-md "<path>"` and use its stdout as the article Markdown. If it fails (file not found, unsupported type, pandoc missing for html/docx), show the error, and ask again — for pandoc missing, also offer that the user can paste the text instead.
   - Pasted text: treat it as Markdown as-is.
   - Keep the original untouched; all edits are made to your working copy.

3. **Review** the working copy against the checklist: the 18 `## ` headings in order, the four-line Environment section, sanitisation, field rules and framing, consistency, and technical accuracy against the skill's reference files. Do not invent facts to fill gaps and do not silently correct anything you cannot verify — report it as "could not verify".

4. **Summarise** the findings in plain chat text, grouped **must-fix**, **should-fix**, **optional**, each with the field it applies to and the proposed change. Then ask: "Accept these recommendations?" (yes / no).

5. **Decide** (all-or-nothing).
   - **Yes:** apply every recommendation to the working copy, show the full revised article, and ask the user to confirm it. Apply edits and re-show if they ask for more.
   - **No:** ask in plain chat text which parts need correction or improvement. Revise accordingly, re-summarise what changed, and go back to the "Accept?" question.

6. **Write** once the user has confirmed the revised article.
   - Take the title from the `## Title` field of the revised article. Run `python3 <skill-dir>/scripts/kcs_render.py --target "<title>"`; its output is the target path without extension (`kcs-drafts/` in the current directory if it exists, otherwise the current directory; existing files get a numeric suffix).
   - Write the revised Markdown to `<target>.md` and run `python3 <skill-dir>/scripts/kcs_render.py <target>.md`. If the renderer rejects the article (headings or Environment), fix the Markdown, show the user what you changed, and re-run. If pandoc is missing, tell the user the `.md` is finished and how to install pandoc; do not hand-write the other formats.
   - Confirm with `ls` that the `.md`, `.docx` and `.html` exist, then list the three file paths. Do not modify or delete the original article. Do not write ticket audit-trail entries.
````

- [ ] **Step 3: Add the README section**

Insert after the "Writing a KCS article" paragraph in `README.md`:

```markdown
### Reviewing a KCS article

`/kcs-review [path]` reviews an article another engineer wrote (`.md`, `.html` or `.docx`, or paste
the text), summarises recommendations (must-fix / should-fix / optional), and on acceptance writes
`kcs-<title-slug>.{md,docx,html}` to `kcs-drafts/` if that folder exists in the working directory,
otherwise to the working directory. The original is never modified. Declining asks which parts need
correction and revises. Needs [pandoc](https://pandoc.org) for html/docx input and for the renders.
```

- [ ] **Step 4: Add the SKILL.md pointer**

After the `## KCS articles` paragraph in `SKILL.md`, add:

```markdown
On `/kcs-review` (see `prompts/kcs-review.md`) or a request to review someone else's KCS article,
read `references/kcs-writing.md` ("Reviewing an article") and import/render with
`scripts/kcs_render.py` (`--to-md`, `--target`). No ticket is involved.
```

- [ ] **Step 5: Verify end to end**

Run:
```bash
python3 -m pytest tests -v
S=skills/marklogic-support/scripts/kcs_render.py; T=$(mktemp -d); cd $T && mkdir kcs-drafts
python3 /Users/martin/Projects/marklogic-support-skill/$S --to-md /Users/martin/Projects/marklogic-support-skill/tests/fixture_kcs/kcs-fixture-problem-example.md > in.md
TARGET=$(python3 /Users/martin/Projects/marklogic-support-skill/$S --target "Fixture: A Title!"); echo $TARGET
cp in.md $TARGET.md && python3 /Users/martin/Projects/marklogic-support-skill/$S $TARGET.md && ls kcs-drafts
```
Expected: tests PASS; `$TARGET` ends in `kcs-drafts/kcs-fixture-a-title`; `ls` shows the `.md`, `.docx` and `.html`.

- [ ] **Step 6: Commit**

```bash
git add prompts/kcs-review.md skills/marklogic-support/references/kcs-writing.md README.md skills/marklogic-support/SKILL.md
git commit -m "feat: /kcs-review command to review and republish another engineer's KCS article

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (done)

- Spec coverage: input (path/paste, html/docx via pandoc, pandoc-missing handling) → Task 2 + prompt step 2; review checklist and severity → Task 3 Step 1 + prompt step 3–4; all-or-nothing decision → prompt step 5; title-derived filenames, `kcs-drafts/` fallback, no overwrite, suffixing → Task 1 + prompt step 6; rendering reuse → prompt step 6; README/SKILL pointers → Task 3; testing items (round trip, slug, collision, dir selection) → Tasks 1–2.
- Placeholders: none. Names consistent: `slugify`, `title_of`, `output_dir`, `unique_stem`, `import_markdown`, `require_pandoc`, flags `--target`, `--cwd`, `--to-md`.
