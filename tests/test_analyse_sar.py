import csv, gzip, json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_sar.py"
FIX = Path(__file__).with_name("fixture_sar")
sys.path.insert(0, str(SCRIPT.parent))
import analyse_sar


def tmpdir(test):
    d = tempfile.TemporaryDirectory()
    test.addCleanup(d.cleanup)
    return Path(d.name)


def run(*args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=env)


class AnalyseSarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.out = Path(tmp.name) / "out"
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
        out = tmpdir(self)
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


HDR = "Linux 5.14.0 ({host})\t2026-10-20\t_x86_64_\t({cpu})\n"
CPUH = "CPU %user %nice %system %iowait %steal %idle"


def cpu_row(t, io=0.0, busy=0.0):
    return f"{t} all {busy:.2f} 0.00 0.00 {io:.2f} 0.00 {100 - busy - io:.2f}\n"


def runm(test, text, *extra, name="sar.txt", env=None):
    d = tmpdir(test)
    (d / name).write_text(text)
    r = run(d, "--out", d / "o", *extra, env=env)
    return r, d / "o"


class RolloverTest(unittest.TestCase):
    def test_live_layout_rolls_over_midnight(self):
        text = HDR.format(host="h1", cpu="4 CPU") + "\n"
        for t in ("11:59:50 PM", "11:59:55 PM", "12:00:00 AM", "12:00:05 AM"):
            text += f"{t} {CPUH}\n" + cpu_row(t, busy=95.0) + "\n"
            text += f"{t} pswpin/s pswpout/s\n{t} 0.00 0.00\n\n"
        rows, _ = analyse_sar.parse(text, "x", set())
        cpu = [str(r["ts"]) for r in rows if "%user" in r["m"]]
        self.assertEqual(cpu, ["2026-10-20 23:59:50", "2026-10-20 23:59:55", "2026-10-21 00:00:00", "2026-10-21 00:00:05"])
        swap = [str(r["ts"]) for r in rows if "pswpin/s" in r["m"]]
        self.assertEqual(swap[-1], "2026-10-21 00:00:05")
        f = analyse_sar.find(rows, 2)
        self.assertEqual((f[0]["start"], f[0]["end"], f[0]["samples"]),
                         ("2026-10-20 23:59:50", "2026-10-21 00:00:05", 4))

    def test_restart_after_midnight_keeps_advanced_date(self):
        text = (HDR.format(host="h1", cpu="4 CPU") + f"\n23:50:00 {CPUH}\n" + cpu_row("23:50:00") +
                "00:10:00 LINUX RESTART (4 CPU)\n\n" + f"00:10:00 {CPUH}\n" + cpu_row("00:10:00") + cpu_row("00:20:00"))
        rows, restarts = analyse_sar.parse(text, "x", set())
        self.assertEqual([str(r["ts"]) for r in rows],
                         ["2026-10-20 23:50:00", "2026-10-21 00:10:00", "2026-10-21 00:20:00"])
        self.assertEqual([str(t) for h, t in restarts], ["2026-10-21 00:10:00"])

    def _sections(self, first, second):
        text = HDR.format(host="h1", cpu="4 CPU") + "\n"
        text += f"{first[0]} {CPUH}\n"
        for t in first:
            text += cpu_row(t)
        text += f"\n{second[0]} pswpin/s pswpout/s\n"
        for t in second:
            text += f"{t} 0.00 0.00\n"
        rows, _ = analyse_sar.parse(text, "x", set())
        return rows

    def test_sar_A_second_section_starting_later_than_first_stays_on_base_date(self):
        first = [f"{h:02d}:{m:02d}:01" for h in range(24) for m in range(0, 60, 10)][:-1]   # 00:00:01 .. 23:50:01
        rows = self._sections(first, ["00:10:01", "00:20:01", "00:30:01"])
        self.assertEqual({str(r["ts"])[:10] for r in rows}, {"2026-10-20"})
        self.assertEqual(len(rows), len(first) + 3)

    def test_sar_A_half_day_first_section_then_later_start(self):
        first = [f"{h:02d}:{m:02d}:00" for h in range(0, 12) for m in (0, 30)] + ["12:00:00"]
        rows = self._sections(first, ["00:10:00", "00:40:00"])
        swap = [str(r["ts"]) for r in rows if "pswpin/s" in r["m"]]
        self.assertEqual(swap, ["2026-10-20 00:10:00", "2026-10-20 00:40:00"])

    def test_live_layout_without_midnight_stays_on_base_date(self):
        text = HDR.format(host="h1", cpu="4 CPU") + "\n"
        for t in ("10:00:00", "10:00:05", "10:00:10"):
            text += f"{t} {CPUH}\n" + cpu_row(t) + "\n"
            text += f"{t} pswpin/s pswpout/s\n{t} 0.00 0.00\n\n"
        rows, _ = analyse_sar.parse(text, "x", set())
        self.assertEqual({str(r["ts"])[:10] for r in rows}, {"2026-10-20"})
        self.assertEqual(len(rows), 6)


class DedupeAndRunsTest(unittest.TestCase):
    def test_fixture_copied_twice_gives_identical_findings(self):
        d = tmpdir(self)
        for n in ("a", "b"):
            shutil.copytree(FIX, d / "in" / n)
        one, two = d / "one", d / "two"
        self.assertEqual(run(FIX, "--out", one).returncode, 0)
        self.assertEqual(run(d / "in", "--out", two).returncode, 0)
        self.assertEqual((one / "findings.json").read_text(), (two / "findings.json").read_text())

    def test_identical_block_concatenated_is_not_two_samples(self):
        block = HDR.format(host="h1", cpu="4 CPU") + f"\n10:00:00 {CPUH}\n" + cpu_row("10:00:00", busy=95.0) + \
            cpu_row("10:10:00") + cpu_row("10:20:00")
        r, out = runm(self, block + "\n" + block)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((out / "findings.json").read_text()), [])

    def test_restart_listed_once_across_sections(self):
        sec1 = f"00:00:00 {CPUH}\n" + cpu_row("00:00:00") + "00:05:00 LINUX RESTART (4 CPU)\n\n" + \
            f"00:05:00 {CPUH}\n" + cpu_row("00:05:00") + cpu_row("00:10:00")
        sec2 = "\n00:00:00 pswpin/s pswpout/s\n00:00:00 0.00 0.00\n00:05:00 LINUX RESTART (4 CPU)\n\n" + \
            "00:05:00 pswpin/s pswpout/s\n00:05:00 0.00 0.00\n"
        r, out = runm(self, HDR.format(host="h1", cpu="4 CPU") + "\n" + sec1 + sec2)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out / "SUMMARY.md").read_text().count("2026-10-20 00:05:00"), 1)

    def test_runs_do_not_bridge_gaps_or_restarts(self):
        text = (HDR.format(host="h1", cpu="4 CPU") + f"\n10:00:00 {CPUH}\n" + cpu_row("10:00:00") +
                cpu_row("10:10:00", io=40.0) + "18:15:00 LINUX RESTART (4 CPU)\n\n" + f"18:15:00 {CPUH}\n" +
                cpu_row("18:20:00", io=40.0) + cpu_row("18:30:00") + cpu_row("18:40:00"))
        rows, restarts = analyse_sar.parse(text, "x", set())
        self.assertEqual(analyse_sar.find(rows, 2, restarts), [])
        self.assertEqual(analyse_sar.find(rows, 2), [])            # the gap alone also closes the run
        self.assertEqual(len(analyse_sar.find(rows, 1, restarts)), 2)


class RuleDetailTest(unittest.TestCase):
    def test_mem_available_total_from_percent_memused(self):
        m = {"kbmemfree": 10000.0, "kbavail": 95000.0, "kbmemused": 905000.0, "%memused": 90.5}
        self.assertAlmostEqual(analyse_sar._mem_avail(m, "", 4), 9.5)
        del m["%memused"]
        self.assertAlmostEqual(analyse_sar._mem_avail(m, "", 4), 100.0 * 95000 / 915000)

    def test_notes_when_rules_cannot_fire(self):
        text = ("Linux 5.14.0 (h1)\t2026-10-20\t_x86_64_\n\n10:00:00 kbmemfree kbmemused %memused\n"
                "10:00:00 1000 9000 90.0\n\n10:00:00 runq-sz plist-sz ldavg-1\n10:00:00 9 100 1.0\n")
        r, out = runm(self, text)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = (out / "SUMMARY.md").read_text()
        self.assertIn("mem_available not evaluated: kbavail missing, older sysstat", s)
        self.assertIn("run_queue not evaluated: CPU count unknown", s)


class InputHandlingTest(unittest.TestCase):
    GOOD = HDR.format(host="h1", cpu="4 CPU") + f"\n10:00:00 {CPUH}\n" + cpu_row("10:00:00", io=40.0) + \
        cpu_row("10:10:00", io=40.0)

    def test_binary_next_to_text_is_skipped_with_note(self):
        d = tmpdir(self)
        shutil.copy(FIX / "sar-d1.txt", d / "sar-d1.txt")
        (d / "sa20").write_bytes(b"\x00\x01\x02binary")
        r = run(d, "--out", d / "o", env={"PATH": str(tmpdir(self))})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads((d / "o/findings.json").read_text()))
        s = (d / "o/SUMMARY.md").read_text()
        self.assertIn("skipped binary file", s)
        self.assertIn("sysstat not installed", s)

    def test_no_sar_data_mentions_locale(self):
        d = tmpdir(self); (d / "n.txt").write_text("hello\n")
        r = run(d, "--out", d / "o")
        self.assertIn("no SAR data", r.stderr)
        self.assertIn("LC_ALL=C S_TIME_FORMAT=ISO", r.stderr)
        self.assertIn("locale", r.stderr)

    def test_utf8_bom_is_stripped(self):
        d = tmpdir(self); (d / "b.txt").write_bytes(b"\xef\xbb\xbf" + self.GOOD.encode())
        r = run(d, "--out", d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((d / "o/findings.json").read_text())[0]["rule"], "cpu_iowait")

    def test_compressed_and_utf16_get_specific_note(self):
        d = tmpdir(self)
        (d / "ok.txt").write_text(self.GOOD)
        (d / "sar.gz").write_bytes(gzip.compress(self.GOOD.encode()))
        (d / "u16.txt").write_bytes(self.GOOD.encode("utf-16"))
        r = run(d, "--out", d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = (d / "o/SUMMARY.md").read_text()
        self.assertIn("compressed/UTF-16 file", s)
        self.assertIn("sar.gz", s)
        self.assertIn("u16.txt", s)
        self.assertNotIn("sysstat not installed", s)
        solo = tmpdir(self); (solo / "sar.gz").write_bytes(gzip.compress(b"x"))
        r = run(solo, "--out", solo / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("decompress", r.stderr)
        self.assertNotIn("not installed", r.stderr)

    def test_hostile_host_name_stays_inside_out_dir(self):
        d = tmpdir(self)
        (d / "in").mkdir(); (d / "in/s.txt").write_text(self.GOOD.replace("(h1)", "(../../x)"))
        out = d / "a" / "b" / "out"
        r = run(d / "in", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p.name for p in out.glob("series-*.csv")], ["series-.._.._x.csv"])
        self.assertFalse(list(d.glob("series-*")) or list((d / "a").glob("series-*")))
        self.assertIn("../../x", (out / "SUMMARY.md").read_text())

    def test_cli_validation(self):
        d = tmpdir(self); (d / "s.txt").write_text(self.GOOD)
        r = run(d, "--min-samples", 0)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--min-samples", r.stderr)
        r = run(d / "missing", "--out", d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("path not found", r.stderr)

    def test_skipped_non_sar_files_listed_capped(self):
        d = tmpdir(self); (d / "s.txt").write_text(self.GOOD)
        for i in range(12):
            (d / f"n{i:02}.log").write_text("not sar\n")
        r = run(d, "--out", d / "o")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = (d / "o/SUMMARY.md").read_text()
        self.assertIn("n00.log", s)
        self.assertNotIn("n11.log", s)
        self.assertIn("and 2 more", s)


class InputErrorTest(unittest.TestCase):
    def test_binary_file_without_sar_asks_for_text_output(self):
        d = tmpdir(self); p = d / "sa20"; p.write_bytes(b"\x00\x01\x02binary")
        r = run(p, "--out", d / "o", env={"PATH": str(tmpdir(self))})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sar -A", r.stderr)
        self.assertIn("S_TIME_FORMAT=ISO", r.stderr)

    def test_no_sar_data_is_an_error(self):
        d = tmpdir(self); (d / "notes.txt").write_text("just some text\n")
        r = run(d, "--out", d / "o")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no SAR data", r.stderr)


if __name__ == "__main__":
    unittest.main()
