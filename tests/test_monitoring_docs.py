import subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
MON = SKILL / "references/monitoring.md"
SOURCES = SKILL / "references/sources.md"
SKILL_MD = SKILL / "SKILL.md"


class MonitoringReferenceTest(unittest.TestCase):
    def test_reference_has_the_fixed_shape(self):
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(MON)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_at_most_250_lines(self):
        self.assertLessEqual(len(MON.read_text().splitlines()), 250)

    def test_new_facts_present(self):
        text = MON.read_text()
        for s in ["ErrorLog.txt", "_AccessLog.txt", "xdmp:log", "xdmp:forest-counts",
                  "xdmp:forest-status", "xdmp:host-status", "xdmp:request-cancel",
                  "xdmp:request-status", "xdmp:server-status", "System Status",
                  "Forest Status", "abort", "disk space", "URL not supplied"]:
            self.assertIn(s, text, s)

    def test_no_breach_word(self):
        self.assertNotIn("breach", MON.read_text().lower())

    def test_existing_content_survives(self):
        text = MON.read_text()
        for s in ["Monitoring History", "Meters database"]:
            self.assertIn(s, text, s)

    def test_sources_md_section_cites_page(self):
        section = SOURCES.read_text().split("## monitoring.md")[1].split("\n## ")[0]
        self.assertIn("URL not supplied", section)

    def test_skill_routing_row_has_keywords(self):
        rows = [l for l in SKILL_MD.read_text().splitlines() if l.startswith("| monitoring dashboard")]
        self.assertEqual(len(rows), 1)
        self.assertIn("xdmp:server-status", rows[0])
        self.assertIn("log disk space", rows[0])


if __name__ == "__main__":
    unittest.main()
