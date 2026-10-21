import hashlib, re, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
SKILL_MD = (SKILL / "SKILL.md").read_text()
SCRIPTS = ("analyse_pstack.py", "analyse_perf.py")


def section(md, heading):
    m = re.search(r"(?ms)^" + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", md)
    return m.group(1) if m else ""


class PstackPerfModeTest(unittest.TestCase):
    def test_skill_has_mode_section_after_sar_mode(self):
        self.assertIn("## pstack and perf mode\n", SKILL_MD)
        self.assertLess(SKILL_MD.index("## SAR mode"), SKILL_MD.index("## pstack and perf mode"))
        self.assertLess(SKILL_MD.index("## pstack and perf mode"), SKILL_MD.index("## Audit trail"))

    def test_mode_section_content(self):
        s = section(SKILL_MD, "## pstack and perf mode")
        for w in SCRIPTS + ("incident gate", "references/pstack-analysis.md", "SUMMARY.md",
                            "references/performance-data-requests.md", "[unverified — confirm]"):
            self.assertIn(w, s, w)

    def test_mode_section_covers_zips_and_the_host_overview(self):
        s = section(SKILL_MD, "## pstack and perf mode")
        for w in ("one per host", "zips in zips", "nothing is extracted to disk", "duplicate", "hosts.csv", "overview table"):
            self.assertIn(w, s, w)

    def test_reference_has_several_hosts_section(self):
        ref = (SKILL / "references/pstack-analysis.md").read_text()
        s = section(ref, "## Several hosts")
        for w in ("Host", "Span", "Top finding", "per host", "hosts.csv", "[unverified — confirm]"):
            self.assertIn(w, s, w)
        self.assertLessEqual(len(ref.splitlines()), 160)

    def test_mode_section_covers_raw_perf_data(self):
        s = section(SKILL_MD, "## pstack and perf mode")
        for w in ("perf.data", "--convert", "external tool on customer data", "header inventory", "text report", "not captured the same way"):
            self.assertIn(w, s, w)
        ref = (SKILL / "references/pstack-analysis.md").read_text()
        self.assertIn("not captured the same way", section(ref, "## Several hosts"))
        req = (SKILL / "references/performance-data-requests.md").read_text()
        for w in ("raw `perf.data`", "perf archive", "perf report --header -I --stdio"):
            self.assertIn(w, req, w)
        readme = (ROOT / "README.md").read_text()
        for w in ("raw `perf.data`", "--convert"):
            self.assertIn(w, readme, w)

    def test_readme_describes_archive_input(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("diag_inputs.py", readme)
        self.assertIn("zips in zips", readme)

    def test_classification_bullet(self):
        self.assertIn("- A pstack movie (a pstack.log, or the zip from pstack.sh) or a `perf report --stdio` "
                      "text report → **pstack and perf mode**", SKILL_MD)

    def test_triage_mode_points_to_the_mode(self):
        self.assertNotIn("no analysis script yet", SKILL_MD)
        self.assertIn("use **pstack and perf mode**", SKILL_MD)

    def test_routing_row_mentions_both_scripts(self):
        row = [l for l in SKILL_MD.splitlines() if l.startswith("|") and "references/pstack-analysis.md" in l]
        self.assertTrue(row)
        for n in SCRIPTS:
            self.assertIn(n, row[0], n)

    def test_audit_trail_names_the_mode(self):
        self.assertIn("pstack and perf", section(SKILL_MD, "## Audit trail"))

    def test_readme_mentions_both_scripts(self):
        readme = (ROOT / "README.md").read_text()
        for n in SCRIPTS:
            self.assertIn(n, readme, n)
        self.assertNotIn("analysis script will follow", readme)

    def test_pstack_reference_passes_check_ref(self):
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(SKILL / "references/pstack-analysis.md")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_data_requests_no_longer_say_planned(self):
        t = (SKILL / "references/performance-data-requests.md").read_text()
        self.assertNotIn("phase 2", t)
        self.assertNotIn("is planned", t)
        for n in SCRIPTS:
            self.assertIn(n, t, n)

    def test_fixture_readmes_exist(self):
        for d in ("fixture_pstack", "fixture_perf"):
            p = ROOT / "tests" / d / "README.md"
            self.assertTrue(p.exists(), d)
            self.assertIn("sanitised", p.read_text())


def _is_binary(data):
    return b"\0" in data[:4096]


def token_hashes_by_file(roots):
    """{path: set of sha256 hex digests of every lower-case [a-z0-9]+ token} for each text file under roots (files or dirs)."""
    out = {}
    for root in roots:
        files = [root] if root.is_file() else sorted(f for f in root.rglob("*") if f.is_file())
        for f in files:
            data = f.read_bytes()
            if _is_binary(data):
                continue
            toks = set(re.findall(r"[a-z0-9]+", data.decode("utf-8", "replace").lower()))
            out[f] = {hashlib.sha256(t.encode()).hexdigest() for t in toks}
    return out


def hits(roots, needle_hashes):
    return sorted(str(f) for f, hs in token_hashes_by_file(roots).items() if hs & set(needle_hashes))


# SHA-256 of customer identifiers that must never appear in the repository (hashes only: the names are not stored here)
FORBIDDEN_TOKEN_HASHES = (
    "f50cf6702e341fa5669e8b4b854d6266fdde35f0bb94aa60d75639d6b3d95998",
    "96a58d9cd1b0510a8559bc2d9b141d5f3f97d38cc8d95cee0f67fc3e5a38049e",
    "a93f4f785d39e3219b1dc7e53fe75343e8fa67e6d05e19afb218fe583d70c509",
)


class HygieneTest(unittest.TestCase):
    def test_no_customer_identifiers_in_skills_tests_docs_readme(self):
        roots = [p for p in (ROOT / "skills", ROOT / "tests", ROOT / "docs", ROOT / "README.md") if p.exists()]
        found = hits(roots, FORBIDDEN_TOKEN_HASHES)
        self.assertEqual(found, [])
        self.assertGreater(len(token_hashes_by_file(roots)), 10)

    def test_the_mechanism_catches_a_hit_and_skips_binary(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            token = "zq7madeuptoken"
            needle = hashlib.sha256(token.encode()).hexdigest()
            (d / "clean.txt").write_text("nothing to see here\n")
            self.assertEqual(hits([d], [needle]), [])
            (d / "dirty.txt").write_text(f"host: {token.upper()}.example\n")
            self.assertEqual(hits([d], [needle]), [str(d / "dirty.txt")])
            (d / "bin.dat").write_bytes(b"\0" + token.encode())
            self.assertEqual(len(hits([d], [needle])), 1)


if __name__ == "__main__":
    unittest.main()
