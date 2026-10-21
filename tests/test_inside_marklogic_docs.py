"""internals.md and the corrected Inside MarkLogic page cites."""
import re, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
REFS = SKILL / "references"
REF = REFS / "internals.md"
T = REF.read_text()
SKILL_MD = (SKILL / "SKILL.md").read_text()


class InternalsTest(unittest.TestCase):
    def test_shape_and_cap(self):
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(REF)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLessEqual(len(T.splitlines()), 250)

    def test_version_caveat_and_source(self):
        for w in ("Version warning", "MarkLogic 8", "April 2016", "[unverified — confirm for 11/12]",
                  "Inside-MarkLogic-Server.pdf", "not stored in the repository", "paraphrased, never quoted"):
            self.assertIn(w, T, w)

    def test_covers_key_topics(self):
        for w in ("xdmp:estimate", "xdmp:plan", "MVCC", "xdmp:lock-for-update", "declareUpdate", "nascent",
                  "StopKeySet", "distribute timestamps", "flash-backup", "journal archiving", "jagged",
                  "retain until backup", "async replicating", "7998", "retire", "statistical", "bucket",
                  "super-database", "S3", "fast data directory", "large size threshold", "journaling",
                  "Huge Pages", "deadline", "xcc.httpcompliant", "session affinity"):
            self.assertIn(w.lower(), T.lower(), w)

    def test_no_verbatim_book_sentences(self):
        for s in ("MarkLogic Server is the Enterprise NoSQL Database",
                  "Imagine that I give you printouts of 10 documents",
                  "It's a high-performance substitute for having to acquire locks",
                  "Trivia buffs will note that it's the only file"):
            self.assertNotIn(s.lower(), T.lower(), s)

    def test_no_breach_word(self):
        self.assertNotIn("breach", T.lower())

    def test_pdfs_are_not_tracked(self):
        r = subprocess.run(["git", "ls-files", "*.pdf"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")


class CitesTest(unittest.TestCase):
    def all_cites(self):
        out = []
        for p in REFS.glob("*.md"):
            for m in re.finditer(r"Inside MarkLogic(?: Server)?(?: \(PDF[^)]*\))? p\.(\d+)(?:-(\d+))?", p.read_text()):
                out.append((p.name, int(m.group(1)), int(m.group(2) or m.group(1))))
        return out

    def test_every_page_cite_is_inside_the_book(self):
        cites = self.all_cites()
        self.assertTrue(cites)
        for name, a, b in cites:
            self.assertTrue(1 <= a <= b <= 127, (name, a, b))

    def test_corrected_cites(self):
        want = {
            "architecture.md": ["Inside MarkLogic p.19", "Inside MarkLogic p.59", "Inside MarkLogic p.102-103",
                                "Inside MarkLogic p.105", "Inside MarkLogic p.34, p.37, p.120"],
            "app-servers.md": ["Inside MarkLogic p.51, p.109"],
            "memory-and-os.md": ["Inside MarkLogic p.120", "Inside MarkLogic p.49 (footnote 11)"],
            "cluster-hosts-groups.md": ["Inside MarkLogic p.48"],
            "databases-forests.md": ["Inside MarkLogic p.34, p.120"],
        }
        for name, needles in want.items():
            t = (REFS / name).read_text()
            for n in needles:
                self.assertIn(n, t, (name, n))

    def test_known_wrong_cites_are_gone(self):
        arch = (REFS / "architecture.md").read_text()
        for bad in ("Inside MarkLogic p.22 |", "Inside MarkLogic p.102 |", "Inside MarkLogic p.104 |"):
            self.assertNotIn(bad, arch, bad)
        self.assertNotIn("Inside MarkLogic p.46", (REFS / "app-servers.md").read_text())
        self.assertNotIn("Inside MarkLogic p.5 |", (REFS / "cluster-hosts-groups.md").read_text())
        self.assertNotIn("Inside MarkLogic p.119 |", (REFS / "memory-and-os.md").read_text())

    def test_expanded_tree_cache_advice_matches_the_book(self):
        t = (REFS / "memory-and-os.md").read_text()
        row = [l for l in t.splitlines() if "XDMP-EXPNTREECACHEFULL" in l and l.startswith("|")][0]
        self.assertIn("rewrite the query", row)
        self.assertNotIn("[unverified", row)


class WiringTest(unittest.TestCase):
    def test_routing_sources_readme(self):
        row = [l for l in SKILL_MD.splitlines() if l.startswith("|") and "references/internals.md" in l]
        self.assertTrue(row)
        for w in ("MVCC", "deadlock", "xdmp:estimate", "flash backup", "assignment policy"):
            self.assertIn(w, row[0], w)
        self.assertIn("## internals.md", (REFS / "sources.md").read_text())
        self.assertIn("internals", (ROOT / "README.md").read_text())
        self.assertIn("internals.md", (REFS / "resource-consumption.md").read_text())


if __name__ == "__main__":
    unittest.main()
