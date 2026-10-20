import re, shutil, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/kcs_render.py"
FIXTURE = Path(__file__).with_name("fixture_kcs") / "kcs-fixture-problem-example.md"
sys.path.insert(0, str(SCRIPT.parent))
import kcs_render


def run(article, outdir=None):
    cmd = [sys.executable, str(SCRIPT), str(article)] + (["--outdir", str(outdir)] if outdir else [])
    return subprocess.run(cmd, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        r = run(FIXTURE, cls.out)
        assert r.returncode == 0, r.stderr
        cls.html = (cls.out / (FIXTURE.stem + ".html")).read_text()

    def test_html_has_all_headings_in_order(self):
        heads = re.findall(r"<h2[^>]*>(.*?)</h2>", self.html)
        self.assertEqual(heads, kcs_render.FIELDS)

    def test_field_list_is_the_20_scs_fields(self):
        self.assertEqual(len(kcs_render.FIELDS), 20)
        self.assertEqual(kcs_render.FIELDS[:4], ["Title", "URL Name", "Summary", "Validation Status"])
        self.assertEqual(kcs_render.FIELDS[-4:],
                         ["Internal Comments", "Article Category", "Keyword Phrase", "Admin Ticket ID"])

    def test_html_inline_styles(self):
        self.assertIn("Verdana", self.html)
        self.assertIn("background-color:#dde1e5", self.html)
        self.assertIn("Problem/Solution", self.html)

    def test_pre_not_double_styled(self):
        for pre in re.findall(r"<pre.*?</pre>", self.html, re.S):
            self.assertNotIn("<code", pre)

    def test_docx_valid(self):
        with zipfile.ZipFile(self.out / (FIXTURE.stem + ".docx")) as z:
            xml = z.read("word/document.xml").decode()
        for f in kcs_render.FIELDS:
            self.assertIn(f.replace("/", "/"), xml)


class TableTest(unittest.TestCase):
    def test_tables_become_lists(self):
        md = "| IdP | URL |\n|---|---|\n| Okta | `https://x/a|b` |\n\n| A | B | C |\n|---|---|---|\n| `k` | v1 | v2. |\n"
        out = kcs_render.tables_to_lists(md)
        self.assertIn("- **Okta** – `https://x/a|b`\n", out)  # 2-col: value only
        self.assertIn("- **`k`** – *B:* v1. *C:* v2.", out)
        self.assertNotIn("|---", out)

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_html_has_no_table_docx_keeps_it(self):
        d = Path(tempfile.mkdtemp()); p = d / "kcs-t-howto-x.md"
        p.write_text(FIXTURE.read_text().replace("## Notes\n", "## Notes\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"))
        self.assertEqual(run(p).returncode, 0)
        self.assertNotIn("<table", (d / "kcs-t-howto-x.html").read_text())
        with zipfile.ZipFile(d / "kcs-t-howto-x.docx") as z:
            self.assertIn("<w:tbl>", z.read("word/document.xml").decode())


class ValidateTest(unittest.TestCase):
    def test_environment_must_be_four_standard_lines(self):
        d = Path(tempfile.mkdtemp()); p = d / "bad.md"
        p.write_text(FIXTURE.read_text().replace("OS: All supported platforms\\\n", ""))
        r = run(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Environment", r.stderr)

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
    def test_environment_renders_as_four_lines(self):
        d = Path(tempfile.mkdtemp()); self.assertEqual(run(FIXTURE, d).returncode, 0)
        h = (d / (FIXTURE.stem + ".html")).read_text()
        env = re.search(r"Environment</h2>(.*?)<h2", h, re.S).group(1)
        self.assertEqual(env.count("<br"), 3)
        self.assertIn("Product: MarkLogic", env)

    def test_missing_heading_rejected(self):
        d = Path(tempfile.mkdtemp()); p = d / "bad.md"
        p.write_text(FIXTURE.read_text().replace("## Workaround", "## Nope"))
        r = run(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Workaround", r.stderr)


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

    def test_cli_target_empty_title_gives_kcs_article(self):
        d = Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, str(SCRIPT), "--target", "", "--cwd", str(d)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip().endswith("kcs-article"), r.stdout)


class ImportTest(unittest.TestCase):
    def test_html_import_without_pandoc_suggests_pasting(self):
        d = Path(tempfile.mkdtemp()); p = d / "a.html"; p.write_text("<h2>Title</h2>")
        empty = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, str(SCRIPT), "--to-md", str(p)],
                           capture_output=True, text=True, env={"PATH": empty})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("paste", r.stderr)
        self.assertIn("pandoc.org", r.stderr)

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
    def test_html_and_docx_round_trip_to_all_headings(self):
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

    def test_category_without_colon_is_clean_error(self):
        e, _ = issues("Product Group: MarkLogic\\\nArea of Interest: Security",
                      "Product Group: MarkLogic\\\nArea of Interest")
        self.assertTrue(has(e, "Article Category"))

    def test_pronoun_us_only_lowercase(self):
        _, w = issues("Other IdPs have an equivalent", "The US-region IdPs have an equivalent")
        self.assertFalse(any("pronoun" in m for m in w))
        _, w = issues("Other IdPs have an equivalent", "Other IdPs give us an equivalent")
        self.assertTrue(has(w, "Cause"))

    def test_pronoun_in_indented_fence_ignored(self):
        _, w = issues("Other IdPs have an equivalent",
                      "Other IdPs have an equivalent\n\n1. Step\n\n   ```\n   we saw your request\n   ```")
        self.assertFalse(any("pronoun" in m for m in w))

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

    def test_word_breach_is_an_error_in_any_form_and_place(self):
        for bad in ("A breach of the policy", "The data was breached.", "BREACHES occur", "Breaching it"):
            e, _ = issues("Other IdPs have an equivalent", bad + "; other IdPs have an equivalent")
            self.assertTrue(has(e, "Wording"), bad)
        e, _ = issues("Invalid grant_type for provider", "a breach in the log")      # inside a code block
        self.assertTrue(has(e, "Wording"))
        md = FIX.replace("KCS ARTICLE — Problem/Solution", "KCS ARTICLE — breach", 1)  # banner comment
        self.assertTrue(has(kcs_render.content_issues(md)[0], "Wording"))

    def test_breach_lookalikes_are_not_flagged(self):
        e, _ = issues("Other IdPs have an equivalent", "Abreachx and Unbreached words; other IdPs have an equivalent")
        self.assertFalse(has(e, "Wording"))

    def test_wording_error_reports_the_line(self):
        e, _ = issues("Other IdPs have an equivalent", "A breach occurred; other IdPs have an equivalent")
        msg = [m for m in e if m.startswith("Wording")][0]
        self.assertRegex(msg, r"line \d+")


class ContentCliTest(unittest.TestCase):
    def test_breach_blocks_rendering(self):
        d = Path(tempfile.mkdtemp()); p = d / "kcs-t-problem-x.md"
        p.write_text(FIX.replace("Other IdPs have an equivalent", "A breach occurred; other IdPs have an equivalent"))
        r = run(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("breach", r.stderr)
        self.assertFalse((d / "kcs-t-problem-x.html").exists())

    def test_errors_exit_nonzero_before_rendering(self):
        d = Path(tempfile.mkdtemp()); p = d / "kcs-t-problem-x.md"
        p.write_text(FIX.replace("## Defect Number\nN/A", "## Defect Number\n12345"))
        r = run(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Defect Number", r.stderr)
        self.assertFalse((d / "kcs-t-problem-x.html").exists())

    @unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
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


if __name__ == "__main__":
    unittest.main()
