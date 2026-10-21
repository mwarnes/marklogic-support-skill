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


METERS_XQY = DIR / "exportMeters.xqy"
GET_RAW = DIR / "get-raw.sh"
METERS_XQY_SHA256 = "ddcafdab21f1aea5dee8a879d8c5ec461bd142bd112e0df097cfee89bf229f97"
GET_RAW_SHA256 = "be0b593a8af7fd6935cfa259da7ad0d21c9696788a6ee4a8738ff5bbfd940440"


class MetersScriptsTest(unittest.TestCase):
    def test_hashes_pinned(self):
        for f, h in ((METERS_XQY, METERS_XQY_SHA256), (GET_RAW, GET_RAW_SHA256)):
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), h,
                             f"{f.name} changed; if KB 000266887 changed, replace the file, its hash here and the README together")

    def test_nothing_left_in_repo_root(self):
        self.assertFalse((ROOT / "exportMeters.xqy").exists())
        self.assertFalse((ROOT / "get-raw.sh").exists())

    def test_get_raw_parses_and_is_executable(self):
        self.assertTrue(os.access(GET_RAW, os.X_OK))
        r = subprocess.run(["bash", "-n", str(GET_RAW)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_xquery_header(self):
        self.assertTrue(METERS_XQY.read_text().startswith('xquery version "1.0-ml";'))

    def test_key_strings(self):
        x, g = METERS_XQY.read_text(), GET_RAW.read_text()
        for needle in ("$output-dir", "xdmp:zip-create", "xdmp:save"):
            self.assertIn(needle, x, needle)
        for needle in ("mlcp.sh export", "-database Meters", "-output_type archive"):
            self.assertIn(needle, g, needle)

    def test_readme_mentions_article(self):
        text = (DIR / "README.md").read_text()
        for needle in ("000266887", "exporting-metering-data", "exportMeters.xqy", "get-raw.sh"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
