import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/marklogic-support/scripts/analyse_logs.py"
FIX = Path(__file__).with_name("fixture_logs")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


class AnalyseLogsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "out"
        cls.topo = cls.tmp / "topology.json"
        cls.topo.write_text(json.dumps({"hosts": {"1": {"name": "h1.example.com"}},
                                        "forests": {"1": {"name": "F1", "database_name": "Content"}}}))
        r = run(FIX, "--out", cls.out, "--topology", cls.topo)
        assert r.returncode == 0, r.stderr
        cls.stdout = r.stdout

    def read(self, rel):
        return (self.out / rel).read_text()

    # --- Task 1 ---
    def test_inventory_classification_and_hosts(self):
        inv = self.read("INVENTORY.md")
        self.assertIn("| h1/ErrorLog.txt | errorlog | h1 |", inv)
        self.assertIn("| ErrorLog_1.txt | errorlog | unknown |", inv)
        self.assertIn("| messages_h2 | syslog | h2 |", inv)
        self.assertIn("| h1/8002_AccessLog.txt | access | h1 |", inv)
        self.assertIn("| h1/AuditLog.txt | audit | h1 |", inv)
        self.assertIn("| h1/8002_RequestLog.txt | skipped |", inv)
        self.assertIn("year 2026 inferred from ErrorLog", inv)
        self.assertIn("| agent | 5 |", inv)                 # noise counted, not emitted
        self.assertIn("host h2 not in topology", inv)

    def test_events_jsonl_normalisation(self):
        evs = [json.loads(l) for l in self.read("events.jsonl").splitlines()]
        odd = next(e for e in evs if "XDMP-UNEXPECTED" in e["msg"])
        self.assertIn("continuation line two", odd["msg"])          # continuation attached
        self.assertEqual(odd["code"], "XDMP-UNEXPECTED")
        sysml = next(e for e in evs if "Forest Security not mounted" in e["msg"])
        self.assertEqual((sysml["host"], sysml["source"], sysml["level"]), ("h2", "syslog-ml", "unknown"))
        self.assertTrue(sysml["ts"].startswith("2026-08-24 00:45:55"))
        self.assertFalse(any("noise one" in e["msg"] for e in evs))   # agent lines never become events

    # --- Task 2 ---
    def test_timeline_kinds_and_collapse(self):
        t = self.read("TIMELINE.md")
        self.assertIn("| time | host | src | kind | sev | message |", t)
        rows = [l for l in t.splitlines() if l.startswith("| 2026")]
        kinds = [r.split("|")[4].strip() for r in rows]
        for k in ("memory", "clock-skew", "storage", "error-line", "restart", "forest-mount", "quorum", "xdqp", "appserver", "merge-reindex"):
            self.assertIn(k, kinds, k)
        self.assertLess(kinds.index("memory"), len(kinds) - 1 - kinds[::-1].index("restart"))   # memory precedes the Aug-24 restart
        self.assertIn("×2", t)                                              # two Memory low within 60 s
        self.assertIn("×3", t)                                              # three SVC-SOCACC
        self.assertIn("Out of memory", t); self.assertIn("systemd: Starting MarkLogic Server", t)
        self.assertIn("(db: Content)", t)                                   # topology annotation of forest F1
        self.assertNotIn("session-99", t)
        self.assertTrue((self.out / "hosts/h1/TIMELINE.md").exists())
        self.assertTrue((self.out / "hosts/h2/TIMELINE.md").exists())
        self.assertTrue((self.out / "hosts/unknown/TIMELINE.md").exists())

    def test_error_line_catchall_and_refs(self):
        evs = [json.loads(l) for l in self.read("events.jsonl").splitlines()]
        odd = next(e for e in evs if "XDMP-UNEXPECTED" in e["msg"])
        self.assertEqual(odd["kind"], "error-line")
        self.assertFalse(any("session-99" in e["msg"] for e in evs))  # uncatalogued systemd/kernel lines dropped
        slow = next(e for e in evs if "Detecting indexes" in e["msg"])
        self.assertEqual((slow["kind"], slow["ref"]), ("storage", "databases-forests.md"))
        self.assertEqual(next(e for e in evs if "Huge Pages" in e["msg"])["kind"], "memory")
        self.assertEqual(next(e for e in evs if "Detected quorum" in e["msg"])["kind"], "quorum")

    # --- Task 3 ---
    def test_patterns(self):
        p = self.read("PATTERNS.md")
        self.assertIn("## h1 / errorlog", p)
        self.assertIn("| Warning | 3 |", p); self.assertIn("| Debug | 3 |", p)
        self.assertIn("| SVC-SOCACC | 3 |", p)
        self.assertIn("Restarts: 1 (2026-08-24 14:23:40", p)
        self.assertIn("## h2 / syslog-ml", p)

    def test_access_and_audit(self):
        a = self.read("ACCESS.md")
        self.assertIn("## h1 / port 8002", a)
        self.assertIn("| 5xx | 25 |", a); self.assertIn("| 2xx | 7 |", a)
        self.assertIn("| 503 | POST /v1/search | 25 |", a)
        self.assertIn("2026-08-24 11 | 25 | **burst**", a)
        self.assertIn("MyApp/1.0", a)
        u = self.read("AUDIT.md")
        self.assertIn("| authentication-failure | 2 |", u)
        self.assertIn("success=false: 2", u)
        self.assertIn("| bob | 2 |", u)


if __name__ == "__main__":
    unittest.main()