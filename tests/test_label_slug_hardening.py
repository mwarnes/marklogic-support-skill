"""safe_label drops format/unassigned characters, csv_cell is self-contained, and the scripts print/derive safe output names."""
import re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/marklogic-support/scripts"
sys.path.insert(0, str(SCRIPTS))
import diag_inputs as di

CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
SLUG = re.compile(r"^[A-Za-z0-9._-]{1,60}$")


class LabelTest(unittest.TestCase):
    def test_format_unassigned_private_use_dropped(self):
        t = di.safe_label("a‮b​c﻿d\U000e0041ef­g⁦h⁠i")
        self.assertEqual(t, "abcdefghi")

    def test_scripts_preserved(self):
        for s in ("שלום", "中文名", "café résumé"):
            self.assertEqual(di.safe_label(s), s)

    def test_all_format_becomes_question_mark(self):
        self.assertEqual(di.safe_label("‮​﻿"), "?")

    def test_csv_cell_tab_cr(self):
        for c in ("\t", "\r", "=", "+", "-x", "@"):
            self.assertTrue(di.csv_cell(c + "1").startswith("'"), c)
        self.assertEqual(di.csv_cell("-"), "-")


class CliTest(unittest.TestCase):
    def run_cli(self, script, fixture, sub):
        hostile = "a\x1b[31m\x1b]0;x\x07\nb‮.txt"
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / hostile
            shutil.copy(ROOT / "tests" / fixture, src)
            r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), str(src)], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f‮]", r.stdout), repr(r.stdout))
            dirs = list((Path(d) / sub).iterdir())
            self.assertEqual(len(dirs), 1)
            self.assertRegex(dirs[0].name, SLUG)

    def test_pstack(self):
        self.run_cli("analyse_pstack.py", "fixture_pstack/pstack-sample.log", "pstack-analysis")

    def test_perf(self):
        self.run_cli("analyse_perf.py", "fixture_perf/perf-report-sample.txt", "perf-analysis")

    def test_slug_helper(self):
        self.assertEqual(di.slug("../..//x  y"), "x_y")
        self.assertEqual(di.slug("‮"), "analysis")
        self.assertEqual(di.slug("a" * 100), "a" * 60)
        self.assertEqual(di.slug("..hid"), "hid")


if __name__ == "__main__":
    unittest.main()
