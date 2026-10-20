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


if __name__ == "__main__":
    unittest.main()
