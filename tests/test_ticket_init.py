import subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/ticket_init.py"
sys.path.insert(0, str(SCRIPT.parent))
import ticket_init

FILES = ["Analysis.md", "Problems.md", "Required-Diagnostics.md", "Root-Cause.md", "Timeline.md"]


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, cwd=cwd)


class TicketInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_creates_the_five_audit_files_with_title_lines(self):
        r = run("12345", "--root", self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        trail = self.root / "12345" / "audit-trail"
        self.assertEqual(sorted(p.name for p in trail.iterdir()), FILES)
        self.assertEqual((trail / "Timeline.md").read_text(), "# Timeline\n\n")
        self.assertEqual((trail / "Root-Cause.md").read_text(), "# Root-Cause\n\n")
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], str(self.root / "12345"))
        self.assertEqual(lines[1:], FILES)

    def test_never_truncates_existing_files(self):
        run("12345", "--root", self.root)
        f = self.root / "12345" / "audit-trail" / "Analysis.md"
        f.write_text("# Analysis\n\n## 2026-10-20 10:00 — [Diagnosis]\nkept\n")
        self.assertEqual(run("12345", "--root", self.root).returncode, 0)
        self.assertIn("kept", f.read_text())

    def test_rejects_ids_that_could_escape_the_root(self):
        for bad in ("../x", "a/b", "..", "", "-rf", "a b", ".hidden/.."):
            r = run(bad, "--root", self.root)
            self.assertNotEqual(r.returncode, 0, bad)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_accepts_typical_ids(self):
        for ok in ("12345", "ML-2026-10", "case_7.1"):
            self.assertEqual(run(ok, "--root", self.root).returncode, 0, ok)

    def test_default_root_is_the_git_toplevel(self):
        repo = self.root / "repo"; sub = repo / "sub" / "dir"; sub.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        r = run("777", cwd=sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / "777" / "audit-trail" / "Timeline.md").exists())
        self.assertFalse((sub / "777").exists())

    def test_default_root_without_git_is_the_current_directory(self):
        d = self.root / "plain"; d.mkdir()
        self.assertEqual(run("888", cwd=d).returncode, 0)
        self.assertTrue((d / "888" / "audit-trail" / "Timeline.md").exists())

    def test_check_lists_an_existing_ticket_and_never_creates(self):
        r = run("404", "--root", self.root, "--check")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stderr)
        self.assertFalse((self.root / "404").exists())
        run("404", "--root", self.root)
        r = run("404", "--root", self.root, "--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [str(self.root / "404")] + FILES)

    def test_check_rejects_bad_ids(self):
        self.assertNotEqual(run("../x", "--root", self.root, "--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
