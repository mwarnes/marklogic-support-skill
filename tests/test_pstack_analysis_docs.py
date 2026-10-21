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

    def test_at_most_160_lines(self):
        self.assertLessEqual(len(text(REF).splitlines()), 160)

    def test_mentions_required_terms(self):
        t = text(REF)
        for w in ("maintainer notes", "assets/support-scripts/pstack.sh", "ErrorLog.txt", "perf", "mlstat",
                  "incident gate", "000266816", "000268341"):
            self.assertIn(w, t, w)

    def test_describes_both_scripts_and_the_worked_example(self):
        t = text(REF)
        for w in ("analyse_pstack.py", "analyse_perf.py", "Worked example", "workaround", "[unverified"):
            self.assertIn(w, t, w)
        self.assertIn("## Worked example (anonymised, 2015, MarkLogic on EC2)\n", t)
        for w in ("planned", "no analysis script yet"):
            self.assertNotIn(w, t, w)

    def test_no_breach_word(self):
        self.assertNotIn("breach", text(REF).lower())

    def test_skill_routing_row_and_triage(self):
        s = (SKILL / "SKILL.md").read_text()
        row = [l for l in s.splitlines() if l.startswith("|") and "pstack" in l and "sar-analysis.md" in l]
        self.assertTrue(row)
        self.assertIn("references/pstack-analysis.md", row[0])
        self.assertNotIn("no analysis script yet", s)

    def test_sources_section(self):
        s = (SKILL / "references/sources.md").read_text()
        self.assertIn("## pstack-analysis.md\n", s)
        self.assertLess(s.index("## performance-data-requests.md"), s.index("## pstack-analysis.md"))

    CAPTURE = ("anonymised 2015 customer capture used for the worked example and the test fixtures; not kept in the repository")

    def test_provenance_wording(self):
        t = text(REF)
        self.assertNotIn("built only from the maintainer notes", t)
        self.assertIn("built from the maintainer notes plus one anonymised customer capture (the worked example)", t)
        self.assertIn("script author's heuristics", t)
        self.assertIn("derived from one real capture", t)
        for w in ("same place across snapshots", "identical internal stacks"):
            self.assertIn(w, t, w)

    def test_capture_is_listed_in_both_source_lists(self):
        ref_sources = text(REF).split("## Sources\n", 1)[1]
        self.assertIn(self.CAPTURE, ref_sources)
        src = (SKILL / "references/sources.md").read_text()
        sect = src.split("## pstack-analysis.md\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn(self.CAPTURE, sect)

    def test_worked_example_says_the_load_balancer_change_came_earlier(self):
        t = text(REF)
        self.assertIn("had earlier connected the load balancer directly to MarkLogic and then reduced the App Server HTTP timeout "
                      "(and resized and changed cache sizes)", t)
        self.assertNotIn("connected the load balancer directly to MarkLogic, resized", t)

    def test_first_procedure_step_runs_the_scripts(self):
        t = text(REF)
        step = t.split("## Standard procedures\n\n", 1)[1].splitlines()[0]
        self.assertTrue(step.startswith("1. Run `scripts/analyse_pstack.py`"), step)
        for w in ("scripts/analyse_perf.py", "SUMMARY.md", "before reading anything by hand"):
            self.assertIn(w, step)

    def test_fixture_readmes_have_the_right_numbers(self):
        self.assertIn("61 of 582 threads kept", (ROOT / "tests/fixture_pstack/README.md").read_text())
        self.assertIn("trimmed to at most 8 per entry", (ROOT / "tests/fixture_perf/README.md").read_text())
        t = text(REF)
        self.assertIn("first 3 frames", t)
        self.assertIn("lock", t)


if __name__ == "__main__":
    unittest.main()
