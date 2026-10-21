import hashlib, os, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "skills/marklogic-support/assets/support-scripts"
PSTACK = DIR / "pstack.sh"
KB_ORIGINAL_SHA256 = "7664a2c0e7d7e71e6ac7ba280391422b9b4ddaad13bf12182ae00701a400ab21"
PSTACK_SHA256 = "cbd5ad316f28a5e44d53d3da5b8f87633b97870eaecfbb9aa7aa79981d78a58c"


class PstackScriptTest(unittest.TestCase):
    def test_script_matches_the_pinned_hash(self):
        self.assertEqual(hashlib.sha256(PSTACK.read_bytes()).hexdigest(), PSTACK_SHA256,
                         "pstack.sh changed; if the KB article changed, update the script, both hashes and the README together")

    def test_interval_line_is_the_only_difference_from_the_kb_article(self):
        original = PSTACK.read_bytes().replace(b"INTERVAL=5 TIME=$1", b"INTERVAL=3 TIME=$1")
        self.assertEqual(hashlib.sha256(original).hexdigest(), KB_ORIGINAL_SHA256)

    def test_parses_and_is_executable(self):
        self.assertTrue(PSTACK.read_text().startswith("#!/bin/bash\n"))
        self.assertTrue(os.access(PSTACK, os.X_OK))
        r = subprocess.run(["bash", "-n", str(PSTACK)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipIf(getattr(os, "geteuid", lambda: 1)() == 0, "must not run the script as root")
    def test_refuses_to_run_without_root_before_doing_anything(self):
        r = subprocess.run(["bash", str(PSTACK), "1"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("must be run as root", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_script_contains_the_commands_the_requests_rely_on(self):
        text = PSTACK.read_text()
        for needle in ("INTERVAL=5", "/etc/MarkLogic/proc-util.sh pstack", "service MarkLogic pstack",
                       "zip -9 -r /tmp/$TSTAMP.zip /tmp/$TSTAMP"):
            self.assertIn(needle, text, needle)

    def test_readme_names_the_source_and_the_rules(self):
        text = (DIR / "README.md").read_text()
        for needle in ("000266816", "creating-a-pstack-movie-for-support", "INTERVAL=5", "INTERVAL=3",
                       "000268341", "ml-support-dump.sh", "telemetry"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
