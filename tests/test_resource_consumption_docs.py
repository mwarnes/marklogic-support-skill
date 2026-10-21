"""resource-consumption.md: shape, version caveat, wiring, paraphrase-only."""
import re, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REF = SKILL / "references/resource-consumption.md"
T = REF.read_text()
SKILL_MD = (SKILL / "SKILL.md").read_text()


class ResourceConsumptionTest(unittest.TestCase):
    def test_reference_shape_passes_check_ref(self):
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(REF)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_states_the_source_and_version_caveat(self):
        for w in ("Version warning", "MarkLogic 7 and 8", "January 2016", "[unverified — confirm for 11/12]",
                  "fundamentals-of-resource-consumption.pdf", "not stored in the repository", "paraphrased, never quoted"):
            self.assertIn(w, T, w)

    def test_covers_the_key_mechanisms(self):
        for w in ("E-node", "D-node", "64 stands", "XDMP-INMMTREEFULL", "xdmp:cache-status", "partition-busy",
                  "XDMP-EXPNTREECACHEFULL", "XDMP-LISTCACHEFULL", "background-io-limit", "preload-mapped-data",
                  "trailing wildcard", "three-character", "journaling", "fast data directory", "Huge Pages",
                  "swap", "Filtered", "unfiltered", "backlog", "Low disk and high CPU", "High disk and low CPU",
                  "lag limit", "reindexer throttle", "rebalance"):
            self.assertIn(w.lower(), T.lower(), w)

    def test_every_page_cite_is_within_the_paper(self):
        pages = [int(n) for n in re.findall(r"RC p\.(\d+)|Resource Consumption p\.(\d+)", T) for n in n if n]
        pages += [int(n) for m in re.findall(r"p\.(\d+)-(\d+)", T) for n in m]
        self.assertTrue(pages)
        self.assertTrue(all(1 <= p <= 37 for p in pages), sorted(set(pages)))

    def test_no_verbatim_paper_sentences(self):
        # a few distinctive sentences from the paper must not be copied
        for s in ("it is a way of throttling back the I/O used by the merging process",
                  "Swap activity is a symptom of a problem",
                  "Mileage will vary, but CPU should be monitored during ingest",
                  "Unfiltered searches, therefore, are guaranteed to be fast"):
            self.assertNotIn(s.lower(), T.lower(), s)

    def test_no_breach_word_and_within_cap(self):
        self.assertNotIn("breach", T.lower())
        self.assertLessEqual(len(T.splitlines()), 250)

    def test_pdf_is_not_tracked(self):
        r = subprocess.run(["git", "ls-files", "fundamentals-of-resource-consumption.pdf"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")


class WiringTest(unittest.TestCase):
    def test_routing_and_triage(self):
        row = [l for l in SKILL_MD.splitlines() if l.startswith("|") and "references/resource-consumption.md" in l]
        self.assertTrue(row)
        for w in ("resource consumption", "xdmp:cache-status", "XDMP-TOOMANYSTANDS", "capacity planning"):
            self.assertIn(w, row[0], w)
        triage = SKILL_MD.split("## Triage mode")[1].split("## Q&A mode")[0]
        self.assertIn("references/resource-consumption.md", triage)

    def test_related_notes_and_indexes_point_to_it(self):
        for n in ("performance-tuning", "memory-and-os", "databases-forests"):
            self.assertIn("resource-consumption.md", (SKILL / f"references/{n}.md").read_text(), n)
        self.assertIn("## resource-consumption.md", (SKILL / "references/sources.md").read_text())
        self.assertIn("resource-consumption", (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
