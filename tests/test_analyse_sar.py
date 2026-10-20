import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_sar.py"
FIX = Path(__file__).with_name("fixture_sar")
sys.path.insert(0, str(SCRIPT.parent))
import analyse_sar


def run(*args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=env)


class AnalyseSarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        r = run(FIX, "--out", cls.out)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout
        cls.findings = json.loads((cls.out / "findings.json").read_text())

    def test_both_time_formats_parse_into_two_hosts(self):
        s = (self.out / "SUMMARY.md").read_text()
        self.assertIn("| ml-d1.example.com | 8 | 2026-10-20 00:00:01 | 2026-10-20 01:10:01 | 8 | 10 min |", s)
        self.assertIn("| ml-d2.example.com | 8 |", s)          # ISO date, 24-hour times
        self.assertIn("2026-10-20 01:20:01", s)                 # LINUX RESTART marker
        self.assertIn("2 hosts", self.stdout)

    def test_incident_host_findings(self):
        self.assertEqual({f["rule"] for f in self.findings},
                         {"cpu_iowait", "disk_await", "disk_util", "swap_io", "mem_available",
                          "direct_reclaim", "run_queue", "net_errors"})
        self.assertTrue(all(f["host"] == "ml-d1.example.com" for f in self.findings))
        disk = [f for f in self.findings if f["rule"] == "disk_await"][0]
        self.assertEqual((disk["key"], disk["samples"], disk["peak"]), ("sda", 3, 180.0))
        self.assertEqual(disk["start"], "2026-10-20 00:30:01")
        self.assertEqual(disk["end"], "2026-10-20 00:50:01")

    def test_quiet_device_and_clean_host_not_flagged(self):
        self.assertFalse([f for f in self.findings if f["key"] == "sdb"])
        self.assertFalse([f for f in self.findings if f["host"] == "ml-d2.example.com"])

    def test_likely_causes_ranked_before_checks(self):
        sev = [f["severity"] for f in self.findings]
        self.assertEqual(sev, sorted(sev))
        self.assertEqual(sev[0], 0)
        self.assertEqual(sev[-1], 1)

    def test_summary_table_and_limits_section(self):
        s = (self.out / "SUMMARY.md").read_text()
        self.assertIn("cpu_iowait (likely cause)", s)
        self.assertIn("run_queue (check)", s)
        self.assertIn("## What SAR cannot show", s)

    def test_series_csv_for_graphing(self):
        with (self.out / "series-ml-d1.example.com.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 8)
        peak = max(rows, key=lambda r: float(r["iowait"]))
        self.assertEqual((peak["time"], float(peak["iowait"]), float(peak["disk_await_max"])),
                         ("2026-10-20 00:30:01", 35.0, 180.0))

    def test_min_samples_filters_short_runs(self):
        out = Path(tempfile.mkdtemp())
        self.assertEqual(run(FIX, "--out", out, "--min-samples", 4).returncode, 0)
        rules = {f["rule"] for f in json.loads((out / "findings.json").read_text())}
        self.assertEqual(rules, {"mem_available"})              # the only 4-sample run


class ParseTest(unittest.TestCase):
    def test_aliases_midnight_rollover_and_sections_restart_at_first_sample(self):
        text = ("Linux 5.14.0 (h1)\t2026-10-20\t_x86_64_\t(4 CPU)\n\n"
                "23:50:01     CPU      %usr     %nice      %sys   %iowait    %steal      %irq     %soft    %guest    %gnice     %idle\n"
                "23:50:01     all     50.00      0.00     45.00      0.00      0.00      0.00      0.00      0.00      0.00      5.00\n"
                "00:00:01     all     50.00      0.00     45.00      0.00      0.00      0.00      0.00      0.00      0.00      5.00\n"
                "\n"
                "23:50:01  pswpin/s pswpout/s\n23:50:01      0.00      0.00\n00:00:01      0.00      0.00\n")
        rows, restarts = analyse_sar.parse(text, "x", set())
        cpu = [r for r in rows if "%user" in r["m"]]
        self.assertEqual([str(r["ts"]) for r in cpu], ["2026-10-20 23:50:01", "2026-10-21 00:00:01"])
        self.assertEqual(cpu[0]["m"]["%system"], 45.0)           # %sys aliased to %system
        swap = [r for r in rows if "pswpin/s" in r["m"]]
        self.assertEqual(str(swap[0]["ts"]), "2026-10-20 23:50:01")   # second section restarts the clock
        self.assertEqual(restarts, [])
        findings = analyse_sar.find(rows, 2)
        self.assertEqual([f["rule"] for f in findings], ["cpu_busy"])

    def test_12_hour_midnight_and_noon(self):
        text = ("Linux 5.14.0 (h1)\t10/20/2026\t_x86_64_\t(4 CPU)\n\n"
                "11:50:01 PM  pswpin/s pswpout/s\n11:50:01 PM 0.00 0.00\n12:00:01 AM 0.00 0.00\n"
                "11:50:01 AM 0.00 0.00\n12:00:01 PM 0.00 0.00\n")
        rows, _ = analyse_sar.parse(text, "x", set())
        self.assertEqual([r["ts"].hour for r in rows], [23, 0, 11, 12])

    def test_ambiguous_date_is_noted(self):
        notes = set()
        analyse_sar.parse("Linux 5.14.0 (h1)\t10/11/2026\t_x86_64_\t(4 CPU)\n", "x", notes)
        self.assertTrue(any("ambiguous" in n for n in notes))
        notes = set()
        analyse_sar.parse("Linux 5.14.0 (h1)\t20/10/2026\t_x86_64_\t(4 CPU)\n", "x", notes)
        self.assertFalse(notes)


class InputErrorTest(unittest.TestCase):
    def test_binary_file_without_sar_asks_for_text_output(self):
        d = Path(tempfile.mkdtemp()); p = d / "sa20"; p.write_bytes(b"\x00\x01\x02binary")
        r = run(p, "--out", d / "o", env={"PATH": tempfile.mkdtemp()})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sar -A", r.stderr)
        self.assertIn("S_TIME_FORMAT=ISO", r.stderr)

    def test_no_sar_data_is_an_error(self):
        d = Path(tempfile.mkdtemp()); (d / "notes.txt").write_text("just some text\n")
        r = run(d, "--out", d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no SAR data", r.stderr)


if __name__ == "__main__":
    unittest.main()
