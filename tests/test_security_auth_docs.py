import re, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/marklogic-support"
AUTH = SKILL / "references/security-authentication.md"
REQ = SKILL / "references/security-data-requests.md"
SKILL_MD = SKILL / "SKILL.md"
AREAS = ("saml", "oauth", "ldap", "certificate", "https")


class SecurityAuthDocsTest(unittest.TestCase):
    def test_auth_reference_has_the_fixed_shape(self):
        r = subprocess.run(["bash", str(ROOT / "tools/check-ref.sh"), str(AUTH)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_auth_reference_covers_every_scheme_and_says_what_it_is(self):
        t = AUTH.read_text()
        for word in ("LDAP", "Certificate", "OAuth", "SAML", "HTTPS", "Kerberos"):
            self.assertIn(word, t)
        self.assertIn("not** official", t)
        self.assertIn("not in the support dump", t)
        kerb = [l for l in t.splitlines() if l.startswith("| Kerberos")]
        self.assertTrue(kerb)
        for l in kerb:
            self.assertIn("[unverified — confirm]", l)

    def test_requests_offer_both_routes_for_every_gather_area(self):
        t = REQ.read_text()
        self.assertIn("support dump does not carry the security configuration", t)
        self.assertIn("## Route A: gather script", t)
        self.assertIn("## Route B: Management API by hand", t)
        self.assertIn("security incident gate", t)
        for a in AREAS:
            self.assertIn(f"| `{a}` |", t, a)
        for ev in ("External Authenticate", "SAML Response", "OAuth Status", "LDAP Search"):
            self.assertIn(ev, t)
        self.assertIn("replaces the whole list", t)
        self.assertIn("MARKLOGIC_PASS", t)

    def test_requests_never_ask_for_secrets(self):
        t = REQ.read_text()
        self.assertIn("Never send a private key or a live access token", t)
        self.assertIn("never ask for it", t)  # the Kerberos keytab

    def test_skill_md_wires_the_new_references_and_mode(self):
        t = SKILL_MD.read_text()
        self.assertIn("references/security-authentication.md", t)
        self.assertIn("references/security-data-requests.md", t)
        self.assertIn("## Security gather mode", t)
        always = t.split("## Triage mode")[0]
        self.assertIn("Security gather mode", always)
        self.assertIn("reading a security gather report", always)
        self.assertTrue(any(l.startswith("| login fails") for l in t.splitlines()))

    def test_every_script_option_the_requests_use_exists_in_the_gather_script(self):
        script = (SKILL / "assets/support-scripts/ml-security-gather.py").read_text()
        for opt in re.findall(r"`(--[a-z-]+)", REQ.read_text()):
            if opt in ("--user", "--host"):
                continue
            trace = (SKILL / "assets/support-scripts/ml-trace-events.py").read_text()
            self.assertTrue(opt in script or opt in trace, opt)

    def test_support_dump_note_points_at_the_requests(self):
        self.assertIn("security-data-requests.md", (SKILL / "references/supportdump-anatomy.md").read_text())


if __name__ == "__main__":
    unittest.main()
