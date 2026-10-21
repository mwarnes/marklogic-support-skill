import re, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REF = SKILL / "references/pstack-analysis.md"


def text(p):
    return p.read_text() if p.exists() else ""


class PstackAnalysisDocsTest(unittest.TestCase):
    def test_reference_exists_and_passes_check_ref(self):
        self.assertTrue(REF.exists())
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(REF)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_at_most_120_lines(self):
        self.assertLessEqual(len(text(REF).splitlines()), 120)

    def test_mentions_required_terms(self):
        t = text(REF)
        for w in ("maintainer notes", "assets/support-scripts/pstack.sh", "ErrorLog.txt", "perf", "mlstat",
                  "incident gate", "000266816", "000268341"):
            self.assertIn(w, t, w)

    def test_does_not_claim_script_exists(self):
        t = text(REF)
        self.assertIn("planned", t)
        self.assertIn("no analysis script yet", t)

    def test_no_breach_word(self):
        self.assertNotIn("breach", text(REF).lower())

    def test_skill_routing_row_and_triage(self):
        s = (SKILL / "SKILL.md").read_text()
        row = [l for l in s.splitlines() if l.startswith("|") and "pstack" in l and "sar-analysis.md" in l]
        self.assertTrue(row)
        self.assertIn("references/pstack-analysis.md", row[0])
        self.assertTrue(any("pstack-analysis.md" in l and "no analysis script yet" in l for l in s.splitlines()))

    def test_sources_section(self):
        s = (SKILL / "references/sources.md").read_text()
        self.assertIn("## pstack-analysis.md\n", s)
        self.assertLess(s.index("## performance-data-requests.md"), s.index("## pstack-analysis.md"))


if __name__ == "__main__":
    unittest.main()
