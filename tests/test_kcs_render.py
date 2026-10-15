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

    def test_html_has_18_headings_in_order(self):
        heads = re.findall(r"<h2[^>]*>(.*?)</h2>", self.html)
        self.assertEqual(heads, kcs_render.FIELDS)

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
    def test_missing_heading_rejected(self):
        d = Path(tempfile.mkdtemp()); p = d / "bad.md"
        p.write_text(FIXTURE.read_text().replace("## Workaround", "## Nope"))
        r = run(p)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Workaround", r.stderr)


if __name__ == "__main__":
    unittest.main()
