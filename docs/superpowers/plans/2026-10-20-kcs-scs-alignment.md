# KCS Solution Content Standard (SCS) Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the `/kcs` and `/kcs-review` article output into line with the company Solution Content Standard (`KCS_SolutionContentStandard.txt`, the parts that apply to all products or to MarkLogic).

**Architecture:** The article stays a 20-heading Markdown file (canonical) rendered to `.docx` and Salesforce `.html`. `kcs_render.py` gains the deterministic SCS checks (field list, URL derived from title, title/summary length, ID format, category values, manual-only placeholders, pronoun warning); the rules and standard statements live in `kcs-writing.md`; the two prompt templates add the new questions and guards.

**Tech Stack:** Python 3 stdlib (`unittest`), pandoc, Markdown prompt templates. Run tests with `python3 -m unittest tests.test_kcs_render` (pytest is not installed).

## Global Constraints

Source of truth: `KCS_SolutionContentStandard.txt`; decisions below were agreed with the user in review discussion.

- **20 fields, exact `## ` headings, in this order:** Title, URL Name, Summary, Validation Status, Article Number, Environment, Question/Problem Description, Steps to Reproduce, Clarifying Information, Error Message, Defect Number, Enhancement Number, Cause, Resolution, Workaround, Notes, Internal Comments, Article Category, Keyword Phrase, Admin Ticket ID.
- **URL Name** = Title (without an `INTERNAL ` prefix), lowercased, every run of non-`[a-z0-9]` replaced by one hyphen, hyphens trimmed. No truncation.
- **Title:** target 55 characters, hard cap 70, not counting an `INTERNAL ` prefix. Renderer warns for 56–70, errors above 70. Error text is trimmed to its key phrase in the title; full text stays in Error Message.
- **Summary:** symptom or question only (never cause/resolution), key words first. Target 160 characters, renderer warns above 160 and errors above 250.
- **Defect Number / Enhancement Number:** `N/A` or comma-separated `MLE-<digits>` ids; renderer errors otherwise.
- **Article Category** is two lines: `Product Group: MarkLogic` (always) and `Area of Interest: <value>` where value is one of `Admin/Config`, `Defects`, `Enhancement`, `Installation`, `Licensing`, `Performance`, `Programming`, `Security`, or empty when unsure. Derived by the skill, shown in the draft review, not asked as a question.
- **Internal Comments** and **Admin Ticket ID** are manual-entry only: the skill always writes a placeholder (a line starting `*(`); renderer errors if either holds anything else. Admin Ticket ID placeholder stays `*(fill in if applicable)*`; Internal Comments placeholder is `*(manual entry)*`. The ticket number never appears in the article body.
- **Hotfix numbers** are never written in the article; release versions go in Resolution. The skill reminds the engineer to add hotfix details to Internal Comments by hand.
- **No Attachment field** and no image/video generation; kcs-writing.md notes these are manual.
- **Types:** `problem`, `howto`, `troubleshoot` (banner `KCS ARTICLE — How to troubleshoot`). Alerts (product-wide or critical defects) are refused with a message.
- **INTERNAL** title prefix only (no INCOMPLETE / stub articles). Forced for security/CVE content.
- **Validation Status** is `Verified` or `Unverified`, derived from evidence and confirmed by the engineer.
- **Style:** present tense, one idea per statement, no personal pronouns. Renderer warns (never fails) on `you/your/yours/we/our/ours/us` outside code.
- **`/kcs-review` severity:** must-fix for rules whose breach makes the article non-compliant or leaks data; should-fix for length and style limits; optional for the 56–70 title band and cosmetics.
- Existing CLI behaviour (`kcs_render.py ARTICLE.md [--outdir]`, `--target`, `--to-md`) keeps working. Validation errors are raised before pandoc is required.
- `kcs-drafts/` and `KCS_SolutionContentStandard.txt` are untracked; do not `git add` them.

---

## File Structure

- Modify `skills/marklogic-support/scripts/kcs_render.py` — `FIELDS` (20), `url_name`, `section`, `content_issues`, validation wiring, `troubleshoot` banner inference.
- Modify `tests/test_kcs_render.py` and `tests/fixture_kcs/kcs-fixture-problem-example.md` — new field list, fixture rewritten to be SCS-compliant, tests for each check.
- Rewrite `skills/marklogic-support/references/kcs-writing.md` — the 20-field standard, standard statements, review checklist.
- Modify `prompts/kcs.md`, `prompts/kcs-review.md`, `README.md`.
- Rewrite (untracked) `kcs-drafts/kcd-md/kcs-04-problem-malformed-request.md` and `kcs-01-howto-authorization-code.md` as reference examples.

---

### Task 1: 20-field list and compliant fixture

**Files:**
- Modify: `skills/marklogic-support/scripts/kcs_render.py:15-18` (`FIELDS`)
- Modify: `tests/fixture_kcs/kcs-fixture-problem-example.md` (full rewrite)
- Test: `tests/test_kcs_render.py` (rename one test)

**Interfaces:**
- Produces: `kcs_render.FIELDS` — list of the 20 headings above, in order. Task 2 builds on it and on the fixture's field text.

- [ ] **Step 1: Rewrite the fixture** — replace the whole file `tests/fixture_kcs/kcs-fixture-problem-example.md` with:

````markdown
<!--
KCS ARTICLE — Problem/Solution
Paste each section below into the matching Salesforce field.
-->

## Title
MarkLogic OAuth: request is otherwise malformed

## URL Name
marklogic-oauth-request-is-otherwise-malformed

## Summary
MarkLogic OAuth 2.0 Authorization Code login returns `invalid_request` "The request is otherwise malformed" before the IdP sign-in page appears.

## Validation Status
Verified

## Article Number
*(assigned by Salesforce on save)*

## Environment
Product: MarkLogic\
Version: All supported versions\
OS: All supported platforms\
Component: Security

## Question/Problem Description
After configuring the OAuth 2.0 Authorization Code flow, browsing to the protected app server redirects to the IdP's authorization endpoint, but the IdP returns an error immediately instead of showing a sign-in page. The browser is returned to the MarkLogic app server URL with `error=invalid_request` and `error_description=The request is otherwise malformed` in the query string.

## Steps to Reproduce
1. Register an OAuth 2.0 / OIDC client for the MarkLogic app server on the IdP with no allowed grant types (in Authentik, an OAuth2 provider created through the REST API without a `grant_types` value).
2. Configure a MarkLogic External Security configuration for the Authorization Code flow using that client's ID and secret, and select it on the HTTPS app server.
3. Browse to the app server in a new private browser window.
4. The IdP returns `invalid_request` / "The request is otherwise malformed" instead of a sign-in page.

## Clarifying Information
**Environment details:** MarkLogic Server 12.1.0 and later; External Security configuration with `oauth-flow-type` = `Authorization code`; Identity Provider whose OAuth 2.0 / OIDC client registration has an allowed grant types setting (reproduced with Authentik 2026.8).

The error text does not name the parameter at fault, so it is easily mistaken for a redirect URI mismatch or a malformed PKCE `code_challenge`. The request reaches the IdP and is rejected before sign-in; MarkLogic receives only the error response on its redirect URI and cannot tell which IdP client setting caused it. The IdP's own log identifies the reason.

## Error Message
Returned to the app server's redirect URI as query parameters:

```
error=invalid_request
error_description=The request is otherwise malformed
```

Authentik server log:

```
Invalid grant_type for provider
```

## Defect Number
N/A

## Enhancement Number
N/A

## Cause
The IdP client registration did not allow the `authorization_code` grant type, so the IdP rejected the authorization request. In Authentik, an OAuth2 provider created through the REST API defaults `grant_types` to an empty list; a provider created with the Admin Interface wizard includes `authorization_code`. Other IdPs have an equivalent per-client setting (for example "Standard flow" in Keycloak, or "Authorization Code" under the application's grant types in Okta).

## Resolution
1. On the IdP, open the OAuth 2.0 / OIDC client used by MarkLogic (the client ID in the External Security configuration's `oauth-client-id`).
2. Enable the **Authorization Code** grant type for that client and save. In Authentik, the provider's `grant_types` must include `authorization_code`.
3. While the client is open, confirm the redirect URI matches the MarkLogic `oauth-redirect-uri` exactly, for example `https://marklogic.example.com:8000` (scheme, host and port, no path). In testing with Authentik, a regular-expression redirect URI that required a path after the port did not match.
4. Retry in a new private browser window. The IdP should show its sign-in page, and after sign-in the browser should return to the app server.

Verified on MarkLogic 12.1.0 with Authentik 2026.8: with `grant_types` empty the Authentik log showed `Invalid grant_type for provider` and the browser received `invalid_request`; after setting `authorization_code` the login completed.

## Workaround
N/A — enabling the grant type on the IdP client is the fix.

## Notes
When an Authorization Code configuration fails before the IdP sign-in page appears, check the IdP client registration (enabled grant types, redirect URI, client ID) and the IdP's log before changing MarkLogic settings.

References to Other Documentation:

MarkLogic Server Security Guide
https://docs.marklogic.com/guide/security

MarkLogic article(s):
- How to configure MarkLogic OAuth 2.0 Authorization Code flow
- MarkLogic OAuth 2.0 Authorization Code login redirects in a loop and never completes

## Internal Comments
*(manual entry)*

## Article Category
Product Group: MarkLogic\
Area of Interest: Security

## Keyword Phrase
MarkLogic OAuth2 Authorization Code invalid_request "request is otherwise malformed" grant type authorization_code IdP client registration redirect URI Authentik

## Admin Ticket ID
*(fill in if applicable)*
````

- [ ] **Step 2: Rename the headings test** — in `tests/test_kcs_render.py` change `test_html_has_18_headings_in_order` to `test_html_has_all_headings_in_order` (body unchanged), and in `test_html_and_docx_round_trip_to_18_headings` change the name to `test_html_and_docx_round_trip_to_all_headings`.

- [ ] **Step 3: Add a count test** — in `RenderTest`, add:

```python
    def test_field_list_is_the_20_scs_fields(self):
        self.assertEqual(len(kcs_render.FIELDS), 20)
        self.assertEqual(kcs_render.FIELDS[:4], ["Title", "URL Name", "Summary", "Validation Status"])
        self.assertEqual(kcs_render.FIELDS[-4:],
                         ["Internal Comments", "Article Category", "Keyword Phrase", "Admin Ticket ID"])
```

- [ ] **Step 4: Run tests to see them fail**

Run: `python3 -m unittest tests.test_kcs_render 2>&1 | tail -15`
Expected: FAIL / ERROR (the renderer still demands the old 18 headings).

- [ ] **Step 5: Update `FIELDS`** in `kcs_render.py` (replace the existing list):

```python
FIELDS = ["Title", "URL Name", "Summary", "Validation Status", "Article Number", "Environment",
          "Question/Problem Description", "Steps to Reproduce", "Clarifying Information",
          "Error Message", "Defect Number", "Enhancement Number", "Cause", "Resolution",
          "Workaround", "Notes", "Internal Comments", "Article Category", "Keyword Phrase",
          "Admin Ticket ID"]
```

Also change the module docstring line `The .md must contain the 18 KCS field headings` to `the 20 KCS field headings`, and the `check_headings` message `the 18 KCS headings` to `the 20 KCS headings`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_kcs_render 2>&1 | tail -5`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add skills/marklogic-support/scripts/kcs_render.py tests/test_kcs_render.py tests/fixture_kcs/kcs-fixture-problem-example.md
git commit -m "feat: kcs_render uses the 20 SCS fields; SCS-compliant fixture

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: SCS content checks in the renderer

**Files:**
- Modify: `skills/marklogic-support/scripts/kcs_render.py` (new functions after `check_environment`; wiring in `main`; banner inference)
- Test: `tests/test_kcs_render.py` (new `ContentTest` class)

**Interfaces:**
- Consumes: `FIELDS`, the Task 1 fixture.
- Produces:
  - `section(md, name) -> str` — body text of `## <name>`, stripped, `""` if absent.
  - `url_name(title) -> str`
  - `content_issues(md) -> tuple[list[str], list[str]]` — `(errors, warnings)`, each message starts with the field name.
  - `AREAS` — list of the 8 allowed Area of Interest values.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_kcs_render.py` (before the `if __name__` line):

```python
FIX = FIXTURE.read_text()
TITLE = "MarkLogic OAuth: request is otherwise malformed"


def issues(old=None, new=None):
    md = FIX.replace(old, new, 1) if old is not None else FIX
    return kcs_render.content_issues(md)


def has(msgs, field):
    return any(m.startswith(field) for m in msgs)


class ContentTest(unittest.TestCase):
    def test_fixture_is_clean(self):
        self.assertEqual(issues(), ([], []))

    def test_url_name(self):
        self.assertEqual(kcs_render.url_name("INTERNAL Foo: Bar/Baz!"), "foo-bar-baz")
        self.assertEqual(kcs_render.url_name("How to set up SAML (Okta)"), "how-to-set-up-saml-okta")

    def test_url_must_match_title(self):
        e, _ = issues("marklogic-oauth-request-is-otherwise-malformed", "marklogic-oauth-malformed")
        self.assertTrue(has(e, "URL Name"))

    def test_internal_prefix_not_in_url_or_length(self):
        t = "INTERNAL " + TITLE
        md = FIX.replace(TITLE, t, 1)
        self.assertEqual(kcs_render.content_issues(md), ([], []))

    def test_title_length_bands(self):
        long60 = "MarkLogic OAuth login fails: request is otherwise malformed"   # 59
        e, w = issues(TITLE, long60)
        self.assertTrue(has(w, "Title")); self.assertFalse(has(e, "Title"))
        too_long = TITLE + " " + "x" * 30
        e, _ = issues(TITLE, too_long)
        self.assertTrue(has(e, "Title"))

    def test_summary_bands(self):
        s = "MarkLogic OAuth 2.0 Authorization Code login returns `invalid_request` \"The request is otherwise malformed\" before the IdP sign-in page appears."
        e, w = issues(s, s + " " + "word " * 12)          # ~200
        self.assertTrue(has(w, "Summary")); self.assertFalse(has(e, "Summary"))
        e, _ = issues(s, s + " " + "word " * 30)           # >250
        self.assertTrue(has(e, "Summary"))

    def test_defect_and_enhancement_ids(self):
        e, _ = issues("## Defect Number\nN/A", "## Defect Number\nMLE-123, MLE-4567")
        self.assertFalse(has(e, "Defect Number"))
        e, _ = issues("## Defect Number\nN/A", "## Defect Number\n12345")
        self.assertTrue(has(e, "Defect Number"))
        e, _ = issues("## Enhancement Number\nN/A", "## Enhancement Number\nPSC00012345")
        self.assertTrue(has(e, "Enhancement Number"))

    def test_category_values(self):
        e, _ = issues("Area of Interest: Security", "Area of Interest:")
        self.assertFalse(has(e, "Article Category"))           # empty is allowed
        e, _ = issues("Area of Interest: Security", "Area of Interest: Networking")
        self.assertTrue(has(e, "Article Category"))
        e, _ = issues("Product Group: MarkLogic", "Product Group: Semaphore")
        self.assertTrue(has(e, "Article Category"))
        e, _ = issues("Product Group: MarkLogic\\\nArea of Interest: Security", "Product Group: MarkLogic")
        self.assertTrue(has(e, "Article Category"))

    def test_manual_fields_must_be_placeholders(self):
        e, _ = issues("## Admin Ticket ID\n*(fill in if applicable)*", "## Admin Ticket ID\n12345")
        self.assertTrue(has(e, "Admin Ticket ID"))
        e, _ = issues("## Internal Comments\n*(manual entry)*", "## Internal Comments\nFixed in hot fix 1.2.3")
        self.assertTrue(has(e, "Internal Comments"))

    def test_pronouns_warn_outside_code_only(self):
        _, w = issues("Other IdPs have an equivalent", "You can set an equivalent; other IdPs have an equivalent")
        self.assertTrue(has(w, "Cause"))
        _, w = issues("Other IdPs have an equivalent", "Other IdPs have `your` equivalent")
        self.assertFalse(has(w, "Cause"))
        _, w = issues("Authentik server log:\n\n```\nInvalid grant_type for provider\n```",
                      "Authentik server log:\n\n```\nwe saw your request\n```")
        self.assertFalse(any("pronoun" in m for m in w))


class ContentCliTest(unittest.TestCase):
    def test_errors_exit_nonzero_before_rendering(self):
        d = Path(tempfile.mkdtemp()); p = d / "kcs-t-problem-x.md"
        p.write_text(FIX.replace("## Defect Number\nN/A", "## Defect Number\n12345"))
        r = run(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Defect Number", r.stderr)
        self.assertFalse((d / "kcs-t-problem-x.html").exists())

    def test_warnings_do_not_block(self):
        d = Path(tempfile.mkdtemp()); p = d / "kcs-t-problem-x.md"
        p.write_text(FIX.replace("Other IdPs have an equivalent", "You can set an equivalent; other IdPs have an equivalent"))
        r = run(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning", r.stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_troubleshoot_type_inferred_from_filename(self):
        d = Path(tempfile.mkdtemp()); p = d / "kcs-t-troubleshoot-x.md"
        p.write_text(re.sub(r"\A<!--.*?-->\n", "", FIX, flags=re.S))
        self.assertEqual(run(p).returncode, 0)
        self.assertIn("KCS ARTICLE — How to troubleshoot", (d / "kcs-t-troubleshoot-x.html").read_text())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_kcs_render.ContentTest tests.test_kcs_render.ContentCliTest 2>&1 | tail -8`
Expected: ERROR — `module 'kcs_render' has no attribute 'content_issues'` (and `url_name`).

- [ ] **Step 3: Implement** — in `kcs_render.py`, after `check_environment`, add:

```python
AREAS = ["Admin/Config", "Defects", "Enhancement", "Installation", "Licensing", "Performance",
         "Programming", "Security"]
PRONOUNS = re.compile(r"\b(you|your|yours|we|our|ours|us)\b", re.I)
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
    labels = [l.split(":", 1)[0] for l in cat]
    if labels != ["Product Group", "Area of Interest"]:
        errors.append("Article Category must be the two lines 'Product Group: MarkLogic' and "
                      f"'Area of Interest: <value or empty>'; found {cat}.")
    else:
        group, area = (l.split(":", 1)[1].strip() for l in cat)
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
        if line.startswith("```"):
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
```

Note: the warning text for pronouns must contain the word `pronoun` (it does) and start with the field name (it does).

- [ ] **Step 4: Wire into `main`** — replace the lines

```python
    require_pandoc()
    md = a.article.read_text()
    check_headings(md)
    check_environment(md)
```

with

```python
    md = a.article.read_text()
    check_headings(md)
    check_environment(md)
    errors, warnings = content_issues(md)
    for w in warnings:
        print(f"kcs_render: warning: {w}", file=sys.stderr)
    if errors:
        sys.exit("kcs_render: SCS content errors:\n  - " + "\n  - ".join(errors))
    require_pandoc()
```

- [ ] **Step 5: Troubleshoot banner inference** — in `main`, replace the `kind = ...` expression with:

```python
    kind = banner.group(1).strip() if banner else (
        "How-To (framed as Problem/Solution per template constraints)" if "-howto-" in stem
        else "How to troubleshoot" if "-troubleshoot-" in stem
        else "Problem/Solution" if "-problem-" in stem else "Article")
```

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m unittest tests.test_kcs_render 2>&1 | tail -8`
Expected: `OK` (all existing plus new tests). If `test_title_length_bands` or `test_summary_bands` fail, print `len()` of the strings used and adjust the test strings, not the thresholds (55 / 70, 160 / 250).

- [ ] **Step 7: Commit**

```bash
git add skills/marklogic-support/scripts/kcs_render.py tests/test_kcs_render.py
git commit -m "feat: kcs_render enforces SCS content rules (title, URL, summary, ids, category, manual fields)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Rewrite `kcs-writing.md` (rules, standard statements, review checklist)

**Files:**
- Modify (full rewrite): `skills/marklogic-support/references/kcs-writing.md`

**Interfaces:**
- Consumes: the Global Constraints above (this document is their human-readable form).
- Produces: section names `## Article type`, `## The 20 fields`, `## Environment format`, `## Standard statements`, `## Validation Status`, `## Article Category`, `## Style rules`, `## Sanitise`, `## Quality gate before rendering`, `## Reviewing an article (used by /kcs-review)` — the prompts in Tasks 4 and 5 refer to these names.

- [ ] **Step 1: Write the file** — replace the whole file with the following:

````markdown
# Writing a compliant KCS article

Written to the company Solution Content Standard (SCS, `KCS_SolutionContentStandard.txt` in the
repo root — the generic and MarkLogic parts only). One article per resolved problem or reusable
procedure. The Markdown file is canonical; `scripts/kcs_render.py` checks it and produces the `.docx`
and Salesforce `.html`. Source material is the ticket's `audit-trail/`.

## File layout and naming

```
<TICKET>/kcs/kcs-<TICKET>-<type>-<short-slug>.md      type = problem | howto | troubleshoot
                                                .docx
                                                .html
```

Start the `.md` with the banner comment (the renderer reuses it in the HTML):

```
<!--
KCS ARTICLE — Problem/Solution     (or: How-To (framed as Problem/Solution per template constraints),
                                    or: How to troubleshoot)
Paste each section below into the matching Salesforce field.
-->
```

Without a banner, `kcs_render.py` infers the type from `-problem-` / `-howto-` / `-troubleshoot-` in the filename.

## Article type

- **Problem/Solution** (SCS "Diagnostic") — a symptom, error or unexpected behaviour with a cause
  and fix or workaround. Title states product + symptom/error.
- **How-To** — a goal, defined by a question that is not a problem. Title starts "How to ...". Uses all
  20 fields: Question/Problem Description is the question, Steps to Reproduce is
  `N/A — this article is a configuration procedure, not a defect.`, Cause/Error/Defect/Enhancement
  fields `N/A` where they do not apply.
- **How to troubleshoot** ("umbrella" article) — an error with several causes or contexts. Title
  starts "How to troubleshoot ...". Question/Problem Description names the error and the contexts it
  occurs in; Cause lists the possible causes; Resolution walks the reader through the checks that
  identify their situation, then the fix for each cause.
- **Alerts are out of scope.** A Product Alert (product-wide issue, release announcement) or Critical
  Alert (serious defect affecting most customers) needs Product Management/Legal approval and a
  separate process. `/kcs` stops and tells the engineer so.
- **Security / CVE content.** Anything that describes a security defect, vulnerability or CVE may be
  published internally only, unless Product Management or the Security team directs otherwise. Write
  the article, prefix the Title with `INTERNAL`, and warn the engineer not to publish externally.

## Title prefix

`INTERNAL ` (one word, then a space) marks an article intended for an internal-only audience, a beta
release, sensitive information or security/CVE content. It is not counted in the title length and is
never part of the URL Name. There is no `INCOMPLETE` / stub article for MarkLogic.

## The 20 fields — exact `## ` headings, in this order, none omitted

| # | Heading | Rule |
| --- | --- | --- |
| 1 | Title | One line, key words first, **55 characters or fewer, 70 at most** (not counting `INTERNAL `). Product + symptom (Problem) or "How to ..." (How-To). Trim error text to its key phrase; the whole message goes in Error Message. |
| 2 | URL Name | The Title (without `INTERNAL `) lowercased, every run of characters other than a–z and 0–9 replaced by one hyphen. No truncation, no ticket number. |
| 3 | Summary | The symptom or question only, key words first, **160 characters or fewer** (renderer errors above 250). Never the cause or resolution. Add detail that does not fit the title and tells similar articles apart. |
| 4 | Validation Status | `Verified` or `Unverified`, per "Validation Status" below. |
| 5 | Article Number | `*(assigned by Salesforce on save)*` |
| 6 | Environment | Company standard, exactly four lines and nothing else — see "Environment format". |
| 7 | Question/Problem Description | Diagnostic: the problem. How-To: the question. Complete thoughts, the user's context restated in technical wording (key words, not a verbatim customer paste). Include relevant log or stack-trace frames only, no customer specifics, and the error message with the trace. Lead in with `Log excerpt from <file> reads:` or `Full stack trace from <process> on <OS> reads:`. |
| 8 | Steps to Reproduce | Numbered, minimal, runnable. **Required** when the issue is easily reproduced, needs no customer code and is not too complex. Otherwise `N/A — <which condition fails>`. How-To: `N/A — ...`. |
| 9 | Clarifying Information | An **Environment details** paragraph first (versions verified, required configuration, third-party product versions), then facts that stay true after the fix: conditions under which the problem does not occur, what it is easily mistaken for and how to tell them apart. When the article cites a defect, also put the "Verified on ..." sentence here (not in Resolution). |
| 10 | Error Message | Verbatim, in a fenced block, stating where it appears. Strip customer-specific names (products, files, hosts). `N/A` if none. |
| 11 | Defect Number | `N/A`, or comma-separated `MLE-<number>`. Include defects closed as "no plans to fix". |
| 12 | Enhancement Number | `N/A`, or comma-separated `MLE-<number>`. |
| 13 | Cause | Confirmed root cause in customer-consumable language, mechanism not just symptom. Use the standard statements below when the cause is unknown or the behaviour is by design. How-To: `N/A`. |
| 14 | Resolution | Numbered steps or bullets with the commands, how to confirm success and how to undo any diagnostics. Defects: the standard statements below. Link a resource that is needed to complete the step in the text; put background reading in Notes. |
| 15 | Workaround | Interim option, or `None. <why>` / `N/A — <fix is the resolution>`. |
| 16 | Notes | Anything that fits no other field, then the reference blocks below. Do not repeat a link already given in another field. |
| 17 | Internal Comments | **Manual entry only.** Always `*(manual entry)*`. |
| 18 | Article Category | Two lines — see "Article Category". |
| 19 | Keyword Phrase | One line of search terms: product, error codes, setting names, key nouns, vendor names. |
| 20 | Admin Ticket ID | **Always** `*(fill in if applicable)*`. The ticket number never appears in the article. |

### Notes layout

```
<free text>

References to Other Documentation:

<Book or page title, section>
<https URL on its own line>

MarkLogic article(s):
- <article title — the engineer converts each to a Smart Link>
```

Omit the "References to Other Documentation" block when there are no document links. Every hyperlink
shows its URL in the displayed text. Link the latest documentation version unless the article is
about a specific version.

## Environment format

The Environment section is the four fields below, one per line (end each line but the last with a
backslash `\` so Markdown keeps the line breaks), with no other text:

```
Product: MarkLogic\
Version: All supported versions\
OS: All supported platforms\
Component: Administration
```

`/kcs` asks the user for each value (option 1 default, option 2 derived from the ticket, option 3
free text): Product `MarkLogic` / `Semaphore`; Version `All supported versions` / the ticket's
version; OS `All supported platforms` / `Linux` or `Windows`; Component `Server` / the affected
area (e.g. `Administration`, `Security`). An article about a defect lists only the versions and
operating systems where the defect is present — never "All supported versions". Free-form
environment detail goes in Clarifying Information, never here.

## Validation Status

`/kcs` proposes one value, names the evidence, and the engineer confirms in the draft review.

- **Verified** only when the audit trail shows at least one of: the customer confirmed the solution
  worked; Support reproduced the problem and the solution; the information is in the product
  documentation; Development confirmed how the product works or was designed (not a suggestion for
  one customer); a defect or enhancement was filed (what is verified is that it was filed).
- **Unverified** otherwise — the solution is believed to work but none of the above is on record.

Never claim more than the audit trail shows. `In research` is not used.

## Article Category

```
Product Group: MarkLogic\
Area of Interest: Security
```

Product Group is always `MarkLogic`. Area of Interest is one of `Admin/Config`, `Defects`,
`Enhancement`, `Installation`, `Licensing`, `Performance`, `Programming`, `Security`, derived from the
article and ticket: a filed defect → `Defects`; a filed enhancement → `Enhancement`; otherwise the
dominant topic (install/upgrade → `Installation`; licence keys → `Licensing`; slowness, memory,
throughput → `Performance`; authentication, SAML/OAuth, certificates, roles → `Security`; XQuery,
JavaScript, REST/Java/Node client code → `Programming`; configuration and administration →
`Admin/Config`). When in doubt leave the value empty (`Area of Interest:`); the field is optional to the engineer.

## Standard statements

Use these wordings exactly (fill the `<...>` parts).

**Cause**

- Unknown: `The exact cause is not known at this time.`
- By design: `This is expected behavior.` followed by one concise sentence saying why.
- Unsupported platform: `The exact cause is not known at this time.` then
  `The behavior described in this article has not been tested or verified by MarkLogic Support. At the time of writing (<Month Year>), <OS or version> is not a supported platform for MarkLogic Server and is therefore not supported.`

**Resolution when a defect is referenced** (state the defect id in Defect Number, not here; hotfix
numbers are never written in the article — the engineer records them in Internal Comments)

- Filed, no fix, no workaround: `None at this time.`
- Filed, no fix, workaround exists: `Until the fix is available, use the workaround below.`
- Fixed in a release: `Fixed in MarkLogic <release>.`
- Fix in a release not yet shipped (only when the defect is neither Scheduled nor in Active Dev for it):
  `The fix for this issue is targeted for an upcoming release <X.Y>.` then
  `As of <today's date>, release <X.Y> is targeted to be released in <Qn CYyyyy>, although dates and content of the release are subject to change.`
  Use calendar quarters and years, never fiscal ones, and no specific day.
- Closed with no plans to fix or unable to reproduce: `The defect was closed as the information provided was not sufficient to reproduce the scenario in-house or the provided workaround was adequately viable.` then
  `If the defect is affecting a current version and the workaround is not viable, please open a new support case with steps to reproduce the issue.`

**Resolution when an enhancement is referenced:** state the enhancement id (in Enhancement Number) and,
if implemented, the release it was implemented in. There is no template text.

## Style rules

- Present tense, short sentences, one idea per sentence, no unnecessary words.
- Impersonal: no "you", "we", "our", no customer narrative, no timeline. Instead of "You should perform a
  backup prior to converting your database" write "Perform a database backup prior to converting the
  database." (The renderer warns on pronouns outside code.)
- Give the command being used when the issue occurs or needed to resolve it.
- Refer to the product documentation for additional information where it applies.
- One complete answer to one problem or goal.
- Setting/field/command/error names in backticks; UI labels in **bold**; UI paths with `→`; bold for
  emphasis. Code and commands in fenced blocks, one per step, with `example.com` hosts; say what to
  substitute.
- Tables are fine in the `.md`/`.docx`; the renderer turns them into bullet lists in the Salesforce `.html`
  (first column bold, then ` – `, then the other columns, labelled with their headers when there are 3+
  columns). Keep table cells short.
- Admin Interface route first, Management API (curl) alternative where one exists; note when an API call
  *replaces* rather than merges.
- State scope honestly: versions verified, "not verified on earlier releases". Hypotheses stay out of Cause.
- Images, attachments and video are added by hand in Salesforce; the skill does not produce them. An image
  must be readable at 500 px wide, cropped to what matters, and have a short description (alt text).
  Attachments must contain no customer data and the article must describe them. Video articles are out
  of scope.

## Sanitise (articles are customer-visible)

Remove or replace: customer/company names, real hostnames and domains (`example.com`), IPs, usernames,
tenant/app/client IDs, secrets/keys/tokens, file paths revealing the customer, support dump contents,
ticket-specific dates. Keep error codes, setting names and generic log lines. **The ticket number does
not appear anywhere in the article.** When unsure whether something identifies the customer, replace it.

## Quality gate before rendering

All 20 headings present once in order; no `TBD`/placeholders; every command runnable as written; Cause
is confirmed (or uses a standard statement); sanitised; Title, Summary and Keyword Phrase match what a
customer would search for; Summary holds no cause or resolution; Internal Comments and Admin Ticket ID are
placeholders; `kcs_render.py` reports no errors and no unexplained warnings.

## Reviewing an article (used by `/kcs-review`)

Review an article written by someone else against everything above, then group findings:

- **must-fix** — breaks the standard or leaks data: missing/misordered/extra headings; Environment not
  exactly the four standard lines; unsanitised customer data (names, hosts, IPs, IDs, secrets) or the
  ticket number anywhere; URL Name not derived from the Title; cause or resolution in Summary; Article
  Category missing or with an invalid value; Defect/Enhancement Number not `MLE-<number>`/`N/A`; Internal
  Comments or Admin Ticket ID filled in; hotfix numbers in the article; wrong or missing standard
  statement for an unknown cause or a defect; unconfirmed Cause stated as fact; security/CVE content
  without the `INTERNAL` prefix; alert-type content; commands that cannot run as written; claims
  contradicted by the skill's reference files.
- **should-fix** — hurts findability, clarity or style: Title over 70 characters (the renderer will not
  render it); Summary over 160 characters (over 250 is likewise not rendered); personal pronouns or
  past/future tense; verbatim customer text in Question/Problem Description; reproducible problem with
  no Steps to Reproduce; `Validation Status` stronger than the evidence (or `Unverified` when the audit
  trail shows a Verified condition); link text without its URL; Notes not in the SCS layout; missing or
  incorrect type banner comment (`<!-- KCS ARTICLE — <type> ... -->`; html/docx imports always lose it);
  weak Keyword Phrase; wrong Problem/Solution vs How-To vs troubleshoot framing; scope/versions not
  stated honestly; missing "substitute these values" notes; no Management API alternative where one
  exists; "Verified on ..." sentence in Resolution of a defect article.
- **optional** — Title of 56–70 characters; wording, bold/backtick conventions, table cell length, step order.

Checks that cannot be settled from the article and the references (a version number, a behaviour
claim, whether a defect exists) are reported as "could not verify" — never silently changed. An imported
article whose headings differ from the 20 fields is mapped only where the match is unambiguous (e.g.
`Problem` → `Question/Problem Description`); otherwise the field is reported missing. An article in the
earlier 18-field format is missing Internal Comments and Article Category: add them as the placeholder
and a derived category, and report that you did.
````

- [ ] **Step 2: Cross-check against the code** — run:

```bash
python3 - <<'E'
import re, sys
sys.path.insert(0, "skills/marklogic-support/scripts")
import kcs_render
t = open("skills/marklogic-support/references/kcs-writing.md").read()
rows = re.findall(r"^\| (\d+) \| ([^|]+?) \|", t, re.M)
names = [n for _, n in rows if n != "Heading"]
assert names == kcs_render.FIELDS, (names, kcs_render.FIELDS)
for a in kcs_render.AREAS:
    assert a in t, a
print("ok")
E
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add skills/marklogic-support/references/kcs-writing.md
git commit -m "docs: kcs-writing.md rewritten to the SCS (20 fields, statements, review tiers)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Update `/kcs` (`prompts/kcs.md`)

**Files:**
- Modify (full rewrite): `prompts/kcs.md`

**Interfaces:**
- Consumes: section names from Task 3 (`Article type`, `Standard statements`, `Validation Status`, `Article Category`, `Environment format`).

- [ ] **Step 1: Write the file** — replace the whole file with:

````markdown
---
description: Write a compliant KCS article (Markdown, Word, Salesforce HTML) from a completed MarkLogic support ticket
argument-hint: [ticket number]
---

This is the `/kcs` workflow the user's own team maintains for turning a finished MarkLogic support ticket into a Knowledge-Centered Support article that follows the company Solution Content Standard (see `/ticket` in `prompts/ticket.md`, which creates the ticket folder and its `audit-trail/`). It reads the ticket's audit trail, drafts an article in the team's fixed 20-field format, and renders it to Markdown, Word and Salesforce HTML. Imperative wording below is only there so steps are executed rather than narrated.

Ticket argument: $1

1. **Resolve the ticket.**
   - If `$1` is non-empty, the ticket is `$1`. Run (shell tool) `PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"; ls "$PROJECT_ROOT/$1/audit-trail/"`. If the directory does not exist, tell the user ticket `$1` was not found under the project root and stop — do not create it (that is `/ticket`'s job).
   - If `$1` is empty, use the ticket opened by `/ticket` earlier in this same session. If `/ticket` was not run in this session, ask the user in plain chat text for an existing ticket number, and stop.
   - Work from `<PROJECT_ROOT>/<TICKET>/` from here on.

2. **Load the skill material.** Read `skills/marklogic-support/references/kcs-writing.md` (locate the skill by checking the same paths as `/ticket` step 2 — pi and Claude Code locations, `~/.claude/skills/marklogic-support/` included; if none exists or the symlink is broken, say so and stop). Set `<skill-dir>` to the directory that holds it. Then read all five files in `<TICKET>/audit-trail/`: `Timeline.md`, `Analysis.md`, `Required-Diagnostics.md`, `Problems.md`, `Root-Cause.md`.

3. **Check the ticket is article-worthy and safe to publish.**
   - If `Root-Cause.md` has no entries beyond its title line, warn the user the cause is not confirmed and a KCS article would be premature; ask (plain chat) whether to continue anyway, and stop unless they say yes. Articles written this way use the standard Cause statement for an unknown cause (`kcs-writing.md`, "Standard statements"), say plainly which parts are unconfirmed, and use `Validation Status: Unverified`.
   - **Alert guard.** If the ticket describes a product-wide issue, a release announcement or a serious defect affecting most customers, tell the user that Product and Critical Alerts follow a separate approval process and stop.
   - **Security guard.** Search the audit trail for `CVE-`, "vulnerability" or a security defect. If found, tell the user the article may only be published to the internal channel unless Product Management or the Security team directs otherwise; the Title will carry the `INTERNAL` prefix.

4. **Choose the type and the audience.** Problem/Solution, How-To or How to troubleshoot, per `kcs-writing.md`. Decide from the evidence; ask the user one plain-chat question only if genuinely ambiguous. Unless the security guard already forced it, ask once whether the article is for internal use only (default no); if yes, the Title gets the `INTERNAL` prefix.

5. **Ask the four Environment values.** The company standard Environment section is exactly four lines (Product, Version, OS, Component). Ask them as four questions — with the structured/multiple-choice question tool if your harness has one (the automatic "Other" entry is option 3), otherwise as numbered plain-chat options with "3. Something else (type it)". Derive option 2 from the audit trail and ticket folder; if nothing supports a derived value, drop option 2 rather than guess.

   | Item | Option 1 (default) | Option 2 (derived from the ticket) | Option 3 |
   | --- | --- | --- | --- |
   | Product | `MarkLogic` | `Semaphore` | Something else — user types the product |
   | Version | `All supported versions` | the version(s) in the ticket, e.g. `12.1.0` | Something else |
   | OS | `All supported platforms` | `Linux` or `Windows`, as the ticket shows | Something else |
   | Component | `Server` | the affected area, e.g. `Administration`, `Security` | Something else |

   Use the answers verbatim in the Environment section (format in `kcs-writing.md`); for a defect article list only the versions and operating systems where the defect is present. Put the free-form environment detail under Clarifying Information as an **Environment details** paragraph.

6. **Defects and enhancements.** Search the audit trail for `MLE-<number>` ids. Confirm with the user (plain chat) each id found, or — if none is found — ask once whether a defect or enhancement was filed for this issue and for its `MLE-<number>`. For each defect ask its state: fixed in a shipped release (which), fix targeted for an unreleased release (which, and the calendar quarter), open with or without a workaround, or closed with no plans to fix / unable to reproduce. Use the matching standard Resolution statement from `kcs-writing.md`. Never write hotfix numbers into the article.

7. **Derive Validation Status and Area of Interest.** Do not ask the user; propose them in the draft. Validation Status follows "Validation Status" in `kcs-writing.md` and the draft must name the evidence for `Verified`. Area of Interest follows "Article Category" (one of the eight values, or empty when in doubt).

8. **Draft** `<TICKET>/kcs/kcs-<TICKET>-<type>-<slug>.md` where `<type>` is `problem`, `howto` or `troubleshoot` (create `kcs/` if needed) following `kcs-writing.md` exactly: all 20 `## ` headings in order; Title of 55 characters or fewer (70 at most); URL Name derived from the Title; a Summary of the symptom or question only; Internal Comments and Admin Ticket ID as their placeholders; no customer names, hosts, IPs, IDs or secrets; the ticket number nowhere in the article. Take facts only from the audit trail and files in the ticket folder; do not invent versions, steps or test results. Show the full draft to the user, with the proposed Validation Status and Area of Interest called out, and list anything you could not source. Wait for their approval or edits; apply edits and re-show if they ask.

9. **Render** once approved: `python3 <skill-dir>/scripts/kcs_render.py <TICKET>/kcs/<file>.md`. Treat each `SCS content errors` line as a defect in the draft: fix the Markdown, tell the user what changed, and re-run. Show the user any `warning:` lines (title/summary over target, pronouns) and fix them unless they ask to keep them. If it reports pandoc missing, tell the user the `.md` is finished and how to install pandoc; do not hand-write the other formats. Confirm all three files exist with `ls`.

10. **Record it** per `references/ticket-auditing.md`: append a `Timeline.md` line ("KCS article drafted: <title>, <folder>"). Do not write an `[Closure]` entry in `Analysis.md` unless the user has confirmed the ticket is closed. Finish by listing the three file paths, then remind the user of the manual steps in Salesforce: fill Admin Ticket ID and Internal Comments (hotfix numbers for a fixed defect, forum or source links, defects closed as "not a bug"), convert each listed MarkLogic article title to a Smart Link, add any attachment or image, and check the Channels setting (`Internal App` only for an `INTERNAL` article).
````

- [ ] **Step 2: Check references** — run `grep -n "Standard statements\|Validation Status\|Article Category\|Environment format" prompts/kcs.md skills/marklogic-support/references/kcs-writing.md | head -20` and confirm each section name used in the prompt exists as a heading in `kcs-writing.md`.

- [ ] **Step 3: Commit**

```bash
git add prompts/kcs.md
git commit -m "feat: /kcs follows the SCS (guards, defect/enhancement, derived status and category)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Update `/kcs-review` and README

**Files:**
- Modify: `prompts/kcs-review.md`
- Modify: `README.md:38-43`

- [ ] **Step 1: Edit `prompts/kcs-review.md`** with these exact replacements (use the Edit tool; each old string occurs once):

1. `It checks the article against the team's 18-field format and sanitisation rules` → `It checks the article against the team's 20-field format, the Solution Content Standard rules in \`kcs-writing.md\`, and sanitisation rules`
2. In step 3, replace `the 18 \`## \` headings in order, the four-line Environment section, sanitisation, field rules and framing, consistency, and technical accuracy against the skill's reference files, and the type banner:` with `the 20 \`## \` headings in order, the four-line Environment section, sanitisation (the ticket number must appear nowhere), the SCS field rules (title and summary length, URL Name derived from the Title, \`MLE-<number>\` ids, Article Category, manual-only Internal Comments and Admin Ticket ID, standard Cause and Resolution statements, style and links), the security/CVE and alert checks, consistency, and technical accuracy against the skill's reference files, and the type banner:`
3. In step 3, replace `(\`Problem/Solution\`, or \`How-To (framed as Problem/Solution per template constraints)\`)` with `(\`Problem/Solution\`, \`How-To (framed as Problem/Solution per template constraints)\`, or \`How to troubleshoot\`)`
4. In step 3, after the sentence ending `report it as "could not verify".` append: ` An article in the earlier 18-field format gets the two missing fields added (placeholder and a derived Area of Interest) — list that as a should-fix change.`
5. In step 6, replace `(\`<!--\`, \`KCS ARTICLE — Problem/Solution\` or \`KCS ARTICLE — How-To (framed as Problem/Solution per template constraints)\`,` with `(\`<!--\`, \`KCS ARTICLE — Problem/Solution\`, \`KCS ARTICLE — How-To (framed as Problem/Solution per template constraints)\` or \`KCS ARTICLE — How to troubleshoot\`,`
6. In step 6, replace `If the renderer rejects the article (headings or Environment), fix the Markdown` with `If the renderer rejects the article (headings, Environment or an \`SCS content errors\` line), fix the Markdown`; and after `If pandoc is missing, tell the user the \`.md\` is finished and how to install pandoc; do not hand-write the other formats.` append ` Show the user any \`warning:\` lines the renderer printed.`
7. At the end of step 6 add a sentence: ` Remind the user of the manual Salesforce steps: Admin Ticket ID, Internal Comments, Smart Links for the listed article titles, attachments/images, and Channels.`

- [ ] **Step 2: Edit `README.md`** — replace `<n>/kcs/kcs-<n>-<problem|howto>-<slug>.{md,docx,html}` with `<n>/kcs/kcs-<n>-<problem|howto|troubleshoot>-<slug>.{md,docx,html}`, and after the paragraph that ends `Needs [pandoc](https://pandoc.org) for the Word/HTML renders.` add a new paragraph:

```
Articles follow the company Solution Content Standard (`KCS_SolutionContentStandard.txt`): 20 fields,
title ≤ 55 characters (70 max), URL derived from the title, short symptom-only summary, standard
Cause/Resolution statements. `kcs_render.py` checks these and prints warnings; Internal Comments and
Admin Ticket ID are always left for manual entry in Salesforce.
```

- [ ] **Step 3: Verify** — run `grep -n "18" prompts/kcs-review.md prompts/kcs.md README.md skills/marklogic-support/SKILL.md`. Expected: only the "earlier 18-field format" mention in `kcs-review.md`.

- [ ] **Step 4: Commit**

```bash
git add prompts/kcs-review.md README.md
git commit -m "feat: /kcs-review enforces the SCS tiers; README documents the standard

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Reference examples and end-to-end check

**Files:**
- Rewrite (untracked, not committed): `kcs-drafts/kcd-md/kcs-04-problem-malformed-request.md` (Problem), `kcs-drafts/kcd-md/kcs-01-howto-authorization-code.md` (How-To)
- Regenerate: the matching `.docx` / `.html` under `kcs-drafts/kcs-word/` and `kcs-drafts/kcs-salesforce/`

- [ ] **Step 1: Rewrite draft 04** — it describes the same article as the test fixture. Replace its content with the full text of `tests/fixture_kcs/kcs-fixture-problem-example.md` (identical article, now SCS-compliant).

- [ ] **Step 2: Rewrite draft 01** — read `kcs-drafts/kcd-md/kcs-01-howto-authorization-code.md` and edit it to the 20-field format using `kcs-writing.md` as the rule set: Title ≤ 55 characters (e.g. `How to configure MarkLogic OAuth 2.0 Authorization Code` is 55 — verify with `python3 -c "print(len('...'))"`); URL Name = `how-to-configure-marklogic-oauth-2-0-authorization-code`; Summary a single question sentence ≤ 160 characters with no answer; move Validation Status after Summary; keep the existing Environment, Resolution and Clarifying Information content; convert "you/your" wording to impersonal present tense; Notes in the SCS layout (documentation title line + URL on its own line, `MarkLogic article(s):` list); add `## Internal Comments` (`*(manual entry)*`), `## Article Category` (`Product Group: MarkLogic`, `Area of Interest: Security`) before Keyword Phrase; `## Admin Ticket ID` as `*(fill in if applicable)*`; remove any ticket number. Do not invent facts that are not already in the draft.

- [ ] **Step 3: Render both and read the output**

```bash
cd kcs-drafts
for n in kcs-04-problem-malformed-request kcs-01-howto-authorization-code; do
  python3 ../skills/marklogic-support/scripts/kcs_render.py kcd-md/$n.md --outdir /tmp/kcs-out || break
done
```
Expected: two "wrote ..." pairs, **no `warning:` lines and no errors**. Fix the drafts (not the thresholds) until that holds. Then copy: `cp /tmp/kcs-out/kcs-04-problem-malformed-request.docx kcs-word/ && cp /tmp/kcs-out/kcs-04-problem-malformed-request.html kcs-salesforce/` and the same for `kcs-01-howto-authorization-code`.

- [ ] **Step 4: Confirm the old drafts now fail** (they are the regression check for the rules): run the renderer over `kcd-md/kcs-0[2367]-*.md`; each should exit non-zero with `Missing: ['Internal Comments', 'Article Category']` or similar. This is expected — they are not rewritten in this plan; tell the user.

- [ ] **Step 5: Full test run**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: `OK`.

- [ ] **Step 6: Final status** — run `git status --short`. Expected: only the untracked `KCS_SolutionContentStandard.txt` and `kcs-drafts/` remain; all other work is committed. No commit in this task (the drafts are untracked by the user's choice).

---

## Self-Review (done)

- **Spec coverage:** points 1 → T2 (`url_name`, check), T3; 2 → T2, T3, T4; 3 → T2, T3; 4 → T1 (fields), T3 (attachment note); 5 → T1, T2, T3; 6 → T2 (`ID_LIST`), T3 statements, T4 step 6; 7 → T3 statements, T4 step 3; 8 → T3 prefix, T4 steps 3–4; 9 → T3, T4 step 7; 10 → T3 types/alert guard, T2 banner, T4 steps 3–4, T5; 11 → T3, T4 step 3, T5; 12 → T3 field 7; 13 → T3 field 8; 14 → T2 pronoun warning, T3; 15 → T3 Notes layout; 16 → no change (stated); 17 → T3 note; 18 → T3 Error Message rule; 19 → T1 order; 20–22 → T3 field 9 and style notes; review tiers → T3, T5; reference examples → T6.
- **Placeholders:** none; every code step has code, every doc step has the text or exact replacements.
- **Name consistency:** `FIELDS`, `AREAS`, `section`, `url_name`, `content_issues`, `ID_LIST`, `PRONOUNS` used identically across tasks; placeholder strings `*(manual entry)*` and `*(fill in if applicable)*` are the same in fixture, renderer tests and docs.
- **Open item for the user:** the uncertified-platform statement uses "MarkLogic Support" wording (SCS names Progress Technical Support); confirm the preferred team name.
