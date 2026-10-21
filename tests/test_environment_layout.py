"""Customer-guide folder layout: host from hosts/<hostname>/, environments() and the mixed-environment note."""
import sys, subprocess, tempfile, unittest, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/marklogic-support/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).parent))
import diag_inputs as di
from test_analyse_pstack import thread, IDLE, BUSY, dated_log
from test_analyse_perf import children_report



def pstack(n):  # distinct bytes per host so the duplicate check keeps every input
    return dated_log("10:00", 5, [thread(1, n, *IDLE), thread(2, n + 1, *BUSY)], [thread(1, n, *IDLE), thread(2, n + 1, *BUSY)])


def perf(n):
    return children_report([(60.0 - n, 60.0 - n, "MarkLogic", "[kernel.kallsyms]", "k", "0xffffffff81036c36"),
                            (10.0, 10.0, "MarkLogic", "MarkLogic", ".", "xdmp::Foo::bar()")])


MARK = "inputs from more than one environment"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d = Path(self.tmp.name)

    def tree(self, files):
        for name, text in files.items():
            p = self.d / "in" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        return self.d / "in"

    def zipped(self, files):
        z = self.d / "in.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for n, t in files.items():
                zf.writestr(n, t)
        return z

    def run_script(self, script, path):
        out = self.d / "out"
        r = subprocess.run([sys.executable, str(SCRIPTS / script), str(path), "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (out / "SUMMARY.md").read_text(encoding="utf-8")


class EnvironmentsTest(Base):
    def srcs(self, files):
        notes = set()
        s = di.walk([self.zipped(files)], notes)
        self.addCleanup(di.close_all, s)
        return s

    def test_distinct_in_order_original_spelling(self):
        s = self.srcs({"Prod/hosts/a/pstack/p.log": "x", "QA/hosts/b/pstack/p.log": "y", "prod/hosts/c/pstack/p.log": "z",
                       "hosts/d/pstack/p.log": "w"})
        self.assertEqual(di.environments(s), ["Prod", "QA"])

    def test_none_and_whole_component_only(self):
        s = self.srcs({"hosts/prodigy/pstack/p.log": "x", "latest/p.log": "y"})
        self.assertEqual(di.environments(s), [])

    def test_host_hint_skips_layout_folders(self):
        for name in ("hosts", "oslogs", "sar", "meters", "monitoring", "performance", "repro", "dump", "cloud", "backups"):
            self.assertIn(name, di.GENERIC)
        s = self.srcs({"Prod/hosts/hostA/pstack/p.log": "x"})
        self.assertEqual(di.host_hint(s[0]), "hostA")


class LayoutTest(Base):
    def pstack_files(self, *pairs):
        f = {}
        for i, (env, host) in enumerate(pairs):
            f[f"{env}/hosts/{host}/pstack/pstack.log"] = pstack(100 + 10 * i)
        return f

    def test_pstack_host_and_single_environment(self):
        files = self.pstack_files(("Prod", "hostA"), ("Prod", "hostB"))
        files["Prod/hosts/hostA/sar/sar.txt"] = "Linux 3.10 (hostA)\n"
        s = self.run_script("analyse_pstack.py", self.zipped(files))
        self.assertIn("| hostA |", s)
        self.assertIn("| hostB |", s)
        self.assertNotIn(MARK, s)

    def test_pstack_two_environments_note(self):
        s = self.run_script("analyse_pstack.py", self.tree(self.pstack_files(("Prod", "hostA"), ("QA", "hostB"))))
        self.assertIn(MARK + " (Prod, QA): the customer guide asks for environments not to be mixed; compare hosts within one environment only", s)

    def test_perf_host_and_single_environment(self):
        files = {f"Prod/hosts/{h}/perf/perf.report": perf(i) for i, h in enumerate(("hostA", "hostB"))}
        files["Prod/hosts/hostA/sar/sar.txt"] = "Linux 3.10 (hostA)\n"
        s = self.run_script("analyse_perf.py", self.zipped(files))
        self.assertIn("| hostA |", s)
        self.assertNotIn(MARK, s)

    def test_perf_two_environments_note(self):
        files = {"Prod/hosts/hostA/perf/perf.report": perf(0), "QA/hosts/hostB/perf/perf.report": perf(1)}
        s = self.run_script("analyse_perf.py", self.tree(files))
        self.assertIn(MARK + " (Prod, QA)", s)


if __name__ == "__main__":
    unittest.main()
