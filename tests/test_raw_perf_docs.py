import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REQ = (SKILL / "references/performance-data-requests.md").read_text()
TITLE = "Raw perf.data received: convert or re-request"


def section(name):
    return REQ.split("## " + name + "\n", 1)[1].split("\n## ", 1)[0]


class RawPerfDocsTest(unittest.TestCase):
    def test_section_sits_between_cpu_profile_and_memory_growth(self):
        heads = [l[3:] for l in REQ.splitlines() if l.startswith("## ")]
        i = heads.index("CPU profile: perf")
        self.assertEqual(heads[i:i + 3], ["CPU profile: perf", TITLE, "Memory growth: pmap"])

    def test_section_content(self):
        s = section(TITLE)
        for needle in ("perf report -i", "perf script -i", "--header -I --stdio", "perf archive", "--convert",
                       "incident gate", "[unverified", "Engineer notes:", "perf-report(1)", "perf-script(1)", "perf-archive(1)"):
            self.assertIn(needle, s, needle)
        self.assertNotIn("breach", s.lower())

    def test_customer_message_has_both_commands_and_no_markers(self):
        s = section(TITLE).split("Engineer notes:")[0]
        msg = "\n".join(l for l in s.splitlines() if l.startswith(">"))
        self.assertIn("perf report -i perf.data --header -I --stdio", msg)
        self.assertIn("perf script -i perf.data", msg)
        self.assertNotIn("[unverified", msg)
        self.assertNotIn("breach", msg.lower())

    def test_cpu_profile_points_to_the_new_section(self):
        self.assertIn(TITLE, section("CPU profile: perf"))

    def test_other_docs_name_the_section(self):
        for p in ("skills/marklogic-support/SKILL.md", "README.md", "skills/marklogic-support/references/pstack-analysis.md"):
            t = (ROOT / p).read_text()
            self.assertIn(TITLE, t, p)
            if p.endswith("pstack-analysis.md"):  # README and SKILL.md legitimately mention the banned word in security text
                self.assertNotIn("breach", t.lower(), p)

    def test_notes_do_not_use_the_banned_word(self):
        import sys
        sys.path.insert(0, str(SKILL / "scripts"))
        import analyse_perf as ap
        self.assertNotIn("breach", (ap.NO_PERF_NOTE + ap.RAW_NOTE).lower())

    def test_skill_output_step_offers_the_customer_message(self):
        t = (SKILL / "SKILL.md").read_text()
        self.assertIn("ready-to-paste customer message", t)

    def test_pstack_reference_within_cap(self):
        self.assertLessEqual(len((SKILL / "references/pstack-analysis.md").read_text().splitlines()), 160)


if __name__ == "__main__":
    unittest.main()
