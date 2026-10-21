import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REQ = SKILL / "references/performance-data-requests.md"
MON = SKILL / "references/monitoring.md"
SOURCES = SKILL / "references/sources.md"
SKILL_MD = SKILL / "SKILL.md"
HEAD = "## Monitoring History data: export the Meters data"


def section():
    return REQ.read_text().split(HEAD)[1].split("\n## ")[0]


class MetersExportDocsTest(unittest.TestCase):
    def test_section_position(self):
        heads = [l[3:] for l in REQ.read_text().splitlines() if l.startswith("## ")]
        i = heads.index(HEAD[3:])
        self.assertEqual(heads[i - 1], "Running requests: request and server status")
        self.assertEqual(heads[i + 1], "Stack samples: pstack movie")

    def test_section_content(self):
        s = section()
        for needle in ("exportMeters.xqy", "get-raw.sh", "Telemetry", "000266887", "incident gate",
                       "meters-export", "Engineer notes:", "$start", "$end", "$batch", "$output-dir",
                       "meters-0.zip"):
            self.assertIn(needle, s, needle)
        self.assertTrue(any(l.startswith("> ") for l in s.splitlines()))

    def test_old_not_covered_note_removed(self):
        self.assertNotIn("Monitoring History export is not covered yet", REQ.read_text())

    def test_monitoring_md(self):
        text = MON.read_text()
        self.assertIn("000266887", text)
        self.assertIn("references/performance-data-requests.md", text)
        self.assertLessEqual(len(text.splitlines()), 250)

    def test_sources(self):
        s = SOURCES.read_text()
        for h in ("## monitoring.md", "## performance-data-requests.md"):
            self.assertIn("000266887", s.split(h)[1].split("\n## ")[0], h)

    def test_skill_md(self):
        t = SKILL_MD.read_text()
        self.assertIn(" For an incident that has already passed, ask for the Monitoring History data instead: "
                      "check Telemetry, otherwise the Meters export (`references/performance-data-requests.md`).", t)
        rows = [l for l in t.splitlines() if l.startswith("|") and "references/performance-data-requests.md" in l]
        self.assertEqual(len(rows), 1)
        self.assertIn("meters export, monitoring history export, telemetry", rows[0].split("|")[1])

    def test_no_breach(self):
        for p in (REQ, MON, SKILL / "assets/support-scripts/README.md"):
            self.assertNotIn("breach", p.read_text().lower())


if __name__ == "__main__":
    unittest.main()
