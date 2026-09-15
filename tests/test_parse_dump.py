import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/parse_dump.py"
FIXTURE = Path(__file__).with_name("fixture_dump.txt")


class ParseDumpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "out"
        r = subprocess.run([sys.executable, str(SCRIPT), str(FIXTURE), "--out", str(cls.out)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout

    def read(self, rel):
        return (self.out / rel).read_text()

    # --- Task 1: split ---
    def test_config_split_per_host(self):
        self.assertTrue((self.out / "config/h1/groups.xml").exists())
        self.assertTrue((self.out / "config/h1/clusters.xml").exists())
        self.assertTrue((self.out / "config/h2/hosts.xml").exists())
        self.assertIn("<groups", self.read("config/h1/groups.xml"))

    def test_status_files(self):
        self.assertIn("Forests:            F1", self.read("status/Database-Topology.txt"))
        fs = self.read("status/Forest-Status.txt")
        self.assertIn("### F1", fs); self.assertIn("<forest-status", fs)
        self.assertIn("h2.example.com", self.read("status/Host-Status.txt"))

    def test_logs_split_and_placeholder_skipped(self):
        log = self.read("logs/h1/ErrorLog.txt")
        self.assertIn("SVC-SOCBIND", log)
        self.assertIn('"looks":"like a title"', log)          # lookalike title kept inside the log
        self.assertIn("Time limit exceeded again", log)       # log not truncated at the lookalike
        self.assertTrue((self.out / "logs/h2/ErrorLog.txt").exists())
        self.assertFalse((self.out / "logs/h1/9000_AccessLog.txt").exists())
        inv = self.read("logs/INVENTORY.md")
        self.assertIn("| h1 | 9000_AccessLog.txt | 0 | skipped (placeholder) |", inv)
        self.assertIn("| h1 | ErrorLog.txt | 7 | yes |", inv)   # 4 log lines + 2 rules + 1 lookalike

    # --- Task 2: model ---
    def test_topology_resolves_ids(self):
        t = json.loads(self.read("topology.json"))
        f1 = next(f for f in t["forests"].values() if f["name"] == "F1")
        self.assertEqual(f1["host_name"], "h1.example.com")
        self.assertEqual(f1["database_name"], "Content")
        sec = next(f for f in t["forests"].values() if f["name"] == "Security")
        self.assertEqual(sec["replica_names"], ["Security-R"])
        self.assertTrue(next(f for f in t["forests"].values() if f["name"] == "Security-R")["is_replica"])
        app = next(s for s in t["appservers"] if s["name"] == "App")
        self.assertEqual(app["database_name"], "Content"); self.assertEqual(app["group_name"], "Default")
        self.assertEqual(t["cluster"]["bootstrap_host_names"], ["h1.example.com"])
        self.assertEqual(t["host_status"]["h2.example.com"]["memory_system_total"], 8000)
        self.assertEqual(t["forest_status"]["F1"]["stand_count"], 2)
        self.assertTrue(t["forest_status"]["F1"]["reindexing"])

    def test_summary_md(self):
        s = self.read("summary.md")
        for needle in ("test-cluster", "| h1 |", "| h2 |", "| Default |", "| NoDB |", "| Content |", "F1"):
            self.assertIn(needle, s)

    # --- Task 3: checks ---
    def findings(self):
        return self.read("findings.md")

    def test_expected_findings_present(self):
        f = self.findings()
        for check in ("even-host-count", "failover-no-replica", "replica-same-host", "cache-vs-ram", "forests-per-host",
                      "appserver-no-db", "app-level-auth-default-user", "dir-creation-automatic",
                      "reindexer-throttle-5", "disk-headroom", "orphan-forest", "empty-database", "encryption-on"):
            self.assertIn(f"| {check} |", f, check)
        self.assertNotIn("| config-drift |", f)          # hosts.xml differs only by timestamp attr
        self.assertNotIn("| forest-oversize |", f)

    def test_findings_details_and_order(self):
        f = self.findings()
        self.assertIn("| high | replica-same-host | forest Security |", f)
        self.assertIn("| medium | failover-no-replica | forest F1 |", f)
        self.assertIn("ha-backup-failover.md", f)
        rows = [l for l in f.splitlines() if l.startswith("| ") and not l.startswith("| Severity") and not l.startswith("| ---")]
        sev = [r.split("|")[1].strip() for r in rows]
        order = {"high": 0, "medium": 1, "low": 2}
        self.assertEqual(sev, sorted(sev, key=lambda x: order.get(x, 999)))
        self.assertNotIn("| medium | failover-no-replica | forest Security-R |", f)   # replicas themselves are not flagged

    # --- Task 4: ErrorLog summary ---
    def test_errorlog_summary(self):
        s = self.read("logs/h1/ERRORLOG-SUMMARY.md")
        self.assertIn("## ErrorLog.txt", s)
        self.assertIn("| Info | 1 |", s); self.assertIn("| Warning | 1 |", s); self.assertIn("| Error | 1 |", s); self.assertIn("| Notice | 1 |", s)
        self.assertIn("| XDMP-EXTIME | 2 |", s); self.assertIn("| SVC-SOCBIND | 1 |", s)
        self.assertIn("Restarts: 1", s)
        self.assertIn("2026-01-01 00:00:01.000 → 2026-01-01 00:00:04.000", s)
        s2 = self.read("logs/h2/ERRORLOG-SUMMARY.md")
        self.assertIn("Restarts: 2", s2)


    def test_degrades_on_partial_dump(self):
        partial = "\n".join([
            "%" * 40, "Report Time:         2026-01-01T00:00:00Z", "Report Scope:        host", "Report Host:         solo.example.com", "%" * 40,
            "%" * 40, "Hostname:            solo.example.com", "%" * 40,
            "=" * 40, "Configuration", "=" * 40,
            "=" * 40, "hosts.xml", "=" * 40, "Validation results: OK", "=" * 40,
            '<hosts xmlns="http://marklogic.com/xdmp/hosts"><host><host-id>1</host-id><group>1</group></host></hosts>',
            "=" * 40, "databases.xml", "=" * 40, "Validation results: OK", "=" * 40,
            "<databases><database><database-id>10</database-id><database-name>Broken</database-name><forests><forest-id>99</forest-id></forests></database>",  # unterminated XML
            "=" * 40, "Log Files", "=" * 40,
            "=" * 40, "/var/opt/MarkLogic/Logs/ErrorLog.txt", "=" * 40,
            "2026-01-01 00:00:01.000 Info: Starting MarkLogic Server 12.0.1", "2026-01-01 00:00:02.000 Info: hello", ""])
        d = Path(tempfile.mkdtemp()); (d / "partial.txt").write_text(partial)
        r = subprocess.run([sys.executable, str(SCRIPT), str(d / "partial.txt"), "--out", str(d / "out")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Report Scope is 'host'", r.stderr)
        t = json.loads((d / "out/topology.json").read_text())
        self.assertTrue(any("databases.xml" in w for w in t["warnings"]), t["warnings"])
        self.assertTrue((d / "out/summary.md").exists()); self.assertTrue((d / "out/findings.md").exists())
        self.assertTrue((d / "out/logs/solo/ERRORLOG-SUMMARY.md").exists())

    def test_forest_sizes_summed_from_stands(self):
        """Real dumps carry disk-size/memory-size/document-count per <stand>, not at forest level."""
        partial = "\n".join([
            "%" * 40, "Report Time:         2026-01-01T00:00:00Z", "Report Scope:        cluster", "Report Host:         h1.example.com", "%" * 40,
            "=" * 40, "Forest Status", "=" * 40, "=" * 40, "F9", "=" * 40,
            '<forest-status xmlns="http://marklogic.com/xdmp/status/forest"><forest-id>9</forest-id><forest-name>F9</forest-name><host-id>101</host-id><state>open</state>'
            '<device-space>1000</device-space><stands><stand><stand-id>1</stand-id><disk-size>180</disk-size><memory-size>9</memory-size><document-count>100</document-count></stand>'
            '<stand><stand-id>2</stand-id><disk-size>20</disk-size><memory-size>1</memory-size><document-count>5</document-count></stand></stands></forest-status>', ""])
        d = Path(tempfile.mkdtemp()); (d / "p.txt").write_text(partial)
        r = subprocess.run([sys.executable, str(SCRIPT), str(d / "p.txt"), "--out", str(d / "out")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        fs = json.loads((d / "out/topology.json").read_text())["forest_status"]["F9"]
        self.assertEqual((fs["disk_size"], fs["memory_size"], fs["document_count"], fs["stand_count"]), (200, 10, 105, 2))


if __name__ == "__main__":
    unittest.main()