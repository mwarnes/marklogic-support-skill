# Support scripts that are given to customers

These scripts are copied from Progress Knowledge Base articles so the engineer can hand the customer the exact file.
`pstack.sh` has **one deliberate change** from the article: `INTERVAL=5` instead of the article script's `INTERVAL=3`
(maintainer decision 2026-10-21; the article text says 5 seconds, but its script uses 3). A customer who downloads the
script from the KB article gets the 3-second version. To re-derive: `tests/test_support_scripts.py` pins the hash of the
original article script and the hash of this file, and a test proves that replacing `INTERVAL=5 TIME=$1` with
`INTERVAL=3 TIME=$1` reproduces the original, so the interval line is the only difference. Do not otherwise edit the
scripts. If the article changes, replace the file, update both hashes here and in `tests/test_support_scripts.py`, and
update this table.

| File | Source of truth | Copied |
| --- | --- | --- |
| `pstack.sh` | KB 000266816 "Creating a pstack movie for support" — https://community.progress.com/s/article/creating-a-pstack-movie-for-support (article dated Oct 15, 2024), with `INTERVAL=5` instead of `INTERVAL=3` | 2026-10-21, pasted by the maintainer (community pages cannot be fetched by the skill); interval changed 2026-10-21 |
| `exportMeters.xqy` | KB 000266887 "Exporting metering data" — https://community.progress.com/s/article/exporting-metering-data (article dated Oct 15, 2024). The URL is built from the article's URL Name `exporting-metering-data` and is not confirmed by the maintainer. | 2026-10-21 verbatim (no changes), pasted/saved by the maintainer (community pages cannot be fetched by the skill) |
| `get-raw.sh` | KB 000266887, as above | 2026-10-21 verbatim (no changes), pasted/saved by the maintainer |
| `ml-security-gather.py` | Written for this skill (ticket 01967797), **not** a KB copy; the "do not edit" rule above does not apply and it has no pinned hash. Master copy: `mwarnes-marklogic-scripts/scripts/Security/` (with its unit tests); this is a copy. Replaces `ml-saml-gather.py` | 2026-10-25 |
| `ml-trace-events.py` | Written for this skill (ticket 01967797), **not** a KB copy; same note | 2026-10-24 |

Hashes (SHA-256): original KB script `7664a2c0e7d7e71e6ac7ba280391422b9b4ddaad13bf12182ae00701a400ab21`; this file `cbd5ad316f28a5e44d53d3da5b8f87633b97870eaecfbb9aa7aa79981d78a58c`.
`exportMeters.xqy` `ddcafdab21f1aea5dee8a879d8c5ec461bd142bd112e0df097cfee89bf229f97`; `get-raw.sh` `be0b593a8af7fd6935cfa259da7ad0d21c9696788a6ee4a8738ff5bbfd940440` (both verbatim, pinned in `tests/test_support_scripts.py`). If KB 000266887 changes, replace the files together with their hashes in the tests and this README.

## pstack.sh

Run as root on the MarkLogic host while the problem is happening: `./pstack.sh 60` records a stack trace of the MarkLogic
process every `INTERVAL=3` seconds for 60 seconds into `/tmp/<HHMMSS-MM-DD-YYYY>/pstack.log` and zips it to
`/tmp/<HHMMSS-MM-DD-YYYY>.zip`. Prerequisites (from the article): `yum -y install pstack sysstat psutils gdb`.

Things to know when sending it:

- **Interval:** this copy samples every 5 seconds (`INTERVAL=5`). The article text says 5 seconds but its own script uses 3, so a customer who downloads the KB copy gets 3-second samples.
- **MarkLogic version:** the script calls `/etc/MarkLogic/proc-util.sh pstack` (MarkLogic 11.3.1 and later, RHEL9-based builds).
  For earlier versions, or 11.3.x builds not based on RHEL9, the script's own comment says to replace that line with
  `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log`.
- **Impact:** pstack pauses the MarkLogic process while it records the threads, which has a performance impact.
- **`ml-support-dump.sh`:** the article also lists a "longer pstack script" said to collect OS-level information, but its
  listing is identical to `pstack.sh` (the maintainer confirmed the community site's copy is a duplicate too), so only
  `pstack.sh` is kept here and it is what customers use. Support dumps are usually generated separately or supplied through
  the telemetry link; OS-level data is requested with the SAR and host-metrics requests in
  `references/performance-data-requests.md`.
- **Alternative:** KB 000268341 "Using perf to understand performance" (https://community.progress.com/s/article/using-perf-to-understand-performance)
  samples instead of pausing the process; see the perf request in `references/performance-data-requests.md`.

## exportMeters.xqy and get-raw.sh (Meters export, KB 000266887)

Both give the raw metering XML files (the Monitoring History data) for a defined period, in place of a backup of the Meters database. The article says the exports can be reloaded into MarkLogic and used with the standard tools. A full Meters backup has all the data but is often very large and hard to transfer, so a time range is usually requested. Telemetry (MarkLogic 9+), when enabled, already sends metering data to Support; check it first. Otherwise Monitoring History must be enabled and have collected data for the incident time. The request text is in `references/performance-data-requests.md`.

### exportMeters.xqy

An XQuery script run in Query Console with the content database set to `Meters`. Four variables at the top are edited by the customer. Verified by reading the script:

- Defaults: `$start` `2018-03-15T00:00:00`; `$end` = `$start + P1D` (or give an exact dateTime); `$batch` 3000 (the comment says to lower it in case of expanded tree errors); `$output-dir` `/tmp`.
- It writes `meters-0.zip`, `meters-1.zip`, ... (one zip per `$batch` documents) with `xdmp:save`, so the files are written on the MarkLogic host that runs the query, and logs each file name to the ErrorLog (`writing <dir>/meters-<n>.zip`). Each save runs in its own transaction through `xdmp:invoke-function`.
- It selects documents with `cts:uris` where the element `{http://marklogic.com/manage/meters}start-time` is greater than `$start` and `end-time` is less than `$end`. Both comparisons are strict, and a document must lie wholly inside the window, so add a margin before and after the incident.
- Privileges: `xdmp:save` lists `http://marklogic.com/xdmp/privileges/xdmp-save` and `xdmp:invoke-function` lists `http://marklogic.com/xdmp/privileges/xdmp-invoke` (function pages); `xdmp:zip-create` lists none. Whether Query Console users need anything else was not tested `[unverified — confirm]`.

### get-raw.sh

A bash script that uses MLCP to export. Needs MLCP installed and an XDBC server on the port. Run as `./get-raw.sh <host> <user> <pass> "<start>" "<end>"`, for example `./get-raw.sh localhost admin admin "2018-04-12T00:00:00" "2018-04-14T00:00:00"` (times in the format `2018-03-14T00:00:00`). Verified by reading the script:

- Arguments in order: host, user, password, start, end. Port is fixed at 8000 (the script comment: the built-in server); edit the `port=` line for another XDBC server.
- Output directory `./meters-export` (relative to the current directory). The script comment says it should not exist beforehand; the MLCP export options page says `-output_file_path` "must not already exist".
- It writes the options file `.metrics` in the current directory (containing `-query_filter` and a JSON query on the `{http://marklogic.com/manage/meters}` elements `period` = `raw` and `period-start-time` greater than start and less than end), prints it, then runs `mlcp.sh export -database Meters -mode local -output_type archive -copy_permissions false -options_file .metrics`.
- `mlcp.sh` must be on the PATH; the script prepends `~/mlcp/bin` to it.
- Observation from reading the script: the password is passed with `-password` on the `mlcp.sh` command line, so it is visible in the process list on that machine. Customers may prefer a temporary account.
- MLCP options (MLCP 12 export options page, read 2026-10-21): `-mode` accepts `local`; `-output_type` is `document` or `archive`; `-copy_permissions` defaults to `true`; `-port` should have an XDBC App Server, default 8000; `-options_file` reads further options from a file. The page lists no required privileges or roles for the export user `[unverified — confirm]`.

## ml-security-gather.py and ml-trace-events.py (security diagnostics: SAML, OAuth, LDAP, HTTPS)

Two Python 3 scripts (standard library only; they call `curl` and, for certificates, `openssl`) that use the Management API
on port 8002. Written for the SAML ticket 01967797 as the basis of a "what to gather for SAML issues" KCS article. The
password is read from the `MARKLOGIC_PASS` environment variable and passed to curl on stdin, never on the command line. Maintainer decision 2026-10-24: both scripts are run as the MarkLogic `admin` user (every ticket is opened by a MarkLogic administrator); they were verified only with `admin`, and the minimum role was not determined.

### ml-security-gather.py (read-only)

`python3 ml-security-gather.py AREA --host <host> --user <user> [--external-security NAME] [--user-name U ...] [--idp-metadata FILE|URL] [--saml-response FILE] [--logs [--minutes N | --start ISO --end ISO]] [--cacert CA | --insecure] [--scheme http|https] [--port 8002]`

`AREA` is `saml`, `oauth`, `ldap` or `https` (2026-10-25: the script was extended from SAML only; `AREA --help` documents each area). It writes `./<area>-gather-<timestamp>/` (`SUMMARY.md` plus the raw JSON of each call) and a `.zip` of it. Verified on a
MarkLogic 12.1.0 test server with authentik as the IdP (2026-10-24):

- Self-documenting (2026-10-25): `--help` prints the full documentation; a wrong or misspelt option, or a missing `--host`/`--user`, prints the same documentation followed by the error (option abbreviations are not accepted). A missing password asks for it on a terminal, otherwise stops with the `export MARKLOGIC_PASS=...` hint. A pre-flight read of `GET /manage/v2` stops with a specific hint for a refused password (401), a non-admin user (403), an unreachable host/port, or an untrusted or non-TLS port, and writes no report; an unknown `--external-security` name stops and lists the profiles that exist. Only `--host` and `--user` are required.
- Partial input (2026-10-25): whatever is left out (user, IdP metadata, SAML response, logs, an IdP certificate that is not stored, an unreadable file) is skipped, and `SUMMARY.md` ends with a **Not collected** table (what, why, which option adds it) and says so at the top. A profile that is not SAML (for example OAuth) is still read: its non-secret settings, certificates (chain check) and bound app servers are reported; the SAML-specific checks and the OAuth-specific checks are not implemented in this version. Verified against the lab with a SAML profile and against a mock OAuth profile; there was no real OAuth profile to test.
- Lists (profiles, roles, hosts) are read from the `list-item` entries only: other `nameref` values in a response point at related objects (the Security database), and reading them as profiles produced a failed call. Roles are read in parallel (60 s down to about 12 s on the lab).
- The cluster version comes from `GET /manage/v2` (`version`); host status has none.
- SAML objects: `GET /manage/v2/external-security` (names in `nameref`) then `.../<name>/properties?format=json`; the `saml-*` settings are under `saml-server`. App servers bound to an object: `GET /manage/v2/servers`, then each `.../servers/<name>/properties?group-id=<group>`, property `external-security`; only matching servers are saved.
- Users and roles: `GET /manage/v2/users/<u>/properties` and `.../roles/<r>/properties` (`external-names`, roles).
- Certificates: SHA-1 and SHA-256 fingerprints, subject, issuer, dates, key size, whether the chain in the stored PEM is complete. A missing issuer is reported as INFO, not a fault: on the test server a SAML login worked with only the IdP signing certificate stored. A self-signed certificate (Microsoft Entra signing certificates are) is its own trust anchor.
- `--logs` (verified in the lab, 2026-10-24): checks that the SAML trace events are on for the group, reads `ErrorLog.txt` for a UTC window through `GET /manage/v2/logs?filename=ErrorLog.txt&host=<host>&format=text&start=..&end=..` and keeps the SAML and external-authentication lines (long request, signature and certificate values removed), and summarises each validation step and error with a hint table. The app server `<port>_AccessLog.txt` cannot be searched by time (`MANAGE-CANNOTSEARCH`), so it is read whole and filtered by the script; its `External User(x) is Mapped to Temp User(x) with Role(s): ...` line (no timestamp, belongs to the next request line) shows the roles the SAML identity received, and 401/403 counts are listed. With authorization `saml` the Group values in the trace are compared with every role's external name (`roles-external-names.json`). Both the browser flow and the `authorization: SAML token=<base64>` header flow were exercised.
- The SP private key and any key containing `private-key`, `password`, `secret` or `passphrase` is replaced by `<removed>` before anything is written. The captured SAML response is never copied to the output.
- The comparison with a captured SAML response (issuer vs `saml-entity-id`, audience vs `saml-issuer`, signed assertion, signing certificate vs stored certificate and metadata, NameID and attribute values vs external names) was only tested on generated data, not on a live login `[unverified — confirm]`. It does not verify the XML signature (that needs `xmlsec1`).

### ml-trace-events.py

`python3 ml-trace-events.py enable|disable|status --host <host> --user <user> [--group Default] [--event NAME ...] [--preset saml|oauth|ldap] [--dry-run]`

Generic: any trace event, not only SAML. Presets: `saml` = SAML, SAML Response, External Authenticate; `oauth`; `ldap`.
Verified on MarkLogic 12.1.0 (2026-10-24): the group properties hold a flat list `"event": ["SAML", ...]` and
`"events-activated"`; a `PUT /manage/v2/groups/<group>/properties` **replaces** the whole list (so the script always sends
the complete list), `"event": []` clears it, and event names are not validated. The `trace-event` / `trace-event-name`
shape is rejected with HTTP 400 `MANAGE-INVALIDPAYLOAD`. `disable` removes only the named events and switches the mechanism
off only if the script switched it on (state in `.ml-trace-events-state.json` in the current directory). Trace events are
written to `ErrorLog.txt` at Info level.

### Areas added 2026-10-25 (verified on MarkLogic 12.1.0 and 11.3.7)

- `oauth`: profile settings (non-secret), the IdP discovery document and JWKS compared with the profile, the IdP's TLS chain and whether MarkLogic's trusted certificate authorities (`GET /manage/v2/certificate-authorities`, matched by key identifier or name) contain it, `--token` (header, claims, RS256 signature against the JWKS key by `kid`, issuer, algorithm, username and role claims against the role external names), OAuth trace and log hints. MarkLogic 11 supports the Resource server flow only, MarkLogic 12 also Authorization code: an Authorization code profile on 11 is reported as a failure (a profile cannot even be created there). The RS256 check was tested only with tokens signed by a test key, not with a real IdP token.
- `ldap`: profile settings (the bind password is removed), certificates in the profile, a handshake to the directory server (LDAPS, or StartTLS when the profile asks for it) with chain, host name, expiry, verification against the CA stored in the profile and against MarkLogic's trusted CAs, user and role external names, LDAP trace and log hints taken from the maintainer's LDAP article. No bind or search against the directory is done (no directory credentials needed).
- `https`: per app server with a certificate template (or `--appserver`): TLS settings (MarkLogic 12 `ssl-min-allow-tls` and `ssl-ciphersuites`; MarkLogic 11 `ssl-disable-*` flags), the certificate template, and a live handshake: chain, host name, expiry, completeness, negotiated protocol and cipher, which protocol versions this machine can negotiate (OpenSSL prints `Protocol: TLSv1` even for a failed handshake, so a negotiated cipher is what counts). Found on the lab: a template with `generate-temp-certificate` true whose port serves only a self-signed temporary certificate.
- Facts learned: `GET /manage/v2/certificate-authorities/<id>` returns parsed fields (subject, validity, `subjectKeyIdentifier`) and no PEM; MarkLogic 11's certificate template `/properties` call returns a 400, the plain template call works on both; the client CA list of an app server is not available through the Management API.

### HTTPS certificate status and duplicate subjects (verified 2026-10-25 on MarkLogic 12.1.0 and 11.3.7)

- `GET /manage/v2/certificates` lists the host certificates and `GET /manage/v2/certificate-authorities` the authorities (including the temporary certificate MarkLogic generates for a template); the `/<id>` call of each returns `template-id`, `template-version`, `temporary`, `authority`, serial, validity, issuer, subject, key identifiers and subject alternative names (no PEM). There is no template status resource (`/status`, `?view=status` give 404/400). The `https` area uses these to label each template's certificate **TEMPORARY** or **PERMANENT**.
- The names in the certificate-authority list are the issuer's name: an imported intermediate is listed under its root's name, so `DigiCert Global Root CA` can appear three times for three different certificates.
- `Duplicate certificate subject found in Security Database` is a Warning logged in pairs. On both test servers one pair is the VeriSign Class 3 and Trust Network certificates (present on a default installation, no key identifier) and the other is a host certificate held by two templates (RSA and EC). What triggers the line was not found.

### Let's Encrypt (Route 53) import checked on MarkLogic 12.1.0 (2026-10-25)

Run through the documented flow against a NEW template and a NEW test app server (both removed afterwards): `certbot renew --dry-run` (staging, Route 53 DNS-01) succeeded; the deploy wrapper (`marklogic-cert-deploy-wrapper.sh --config <test config>` with `RENEWED_LINEAGE` set) pushed the existing Let's Encrypt lineage into the template (HTTP 204); the `https` area then reported the template's certificate as **PERMANENT**, issued by Let's Encrypt, the port serving that certificate, and the host name matching. Findings:

- A template created through the Management API with `generate-temp-certificate` true held **no certificate** (not a temporary one): the app server's TLS handshake failed and the ErrorLog warned `Failed to find server certificate in certificate template <id>` (the id is the template's id). The gather resolves the id to the template name.
- The port sent **only the leaf certificate**: the Let's Encrypt intermediate was not in the served chain, so a client without it cannot verify the connection (`unable to verify the first certificate`). **Tested fix:** importing the issuing CA certificate (`YE1`) into MarkLogic's trusted certificate authorities with `pki:insert-trusted-certificates` (Security database, via `/v1/eval`) made the port send `leaf + YE1` at once, with no restart; with a client that trusts `Root YE` the chain then verified (return code 0, host name verified). Removing it with `pki:delete-certificate` reverted to the leaf only. Putting the intermediate into the certificate import itself does not work: `insert-host-certificates` takes one certificate in `cert` and a bundle (even leaf + intermediate, even on a fresh template) is rejected with HTTP 400 `PKI-BADCERTIFICATE`. The deploy hook reads `cert.pem`, so it cannot send the chain; the intermediate has to be imported as a trusted CA once per issuing CA.
- On the test host the Certbot virtualenv uses Python 3.9, and Certbot and boto3 warn that Python 3.9 support is ending.
- On the test host the deploy configuration named a template (`MarkLogic`) that does not exist on the server, so a real renewal would obtain a certificate and then fail to deploy it. This is specific to that host's configuration.

### SAML authorization rule and the user option (2026-10-26)

- **SAML roles come from role external names.** The roles of a SAML login come from the assertion's Group values matched to the external names of roles; a MarkLogic user's roles and external names are not used. Tested on 11.3.7 (authorization `saml` and `internal`, a fresh login each time, cache-timeout 1 s): with a role external name equal to a Group value both settings granted the role (HTTP 200); with no matching role both gave `Mapped to Temp User(x) with Role(s):` empty (HTTP 403); a user external name equal to the NameID, a same-named internal user, or both gave no roles. MarkLogic reports that `internal` is no longer supported on 11.3.7 and 12.1; it was not reproduced on 11.3.7 and not retested on 12.1. The `saml` area warns about authorization other than `saml` (guidance, not a failure) and fails when no role has an external name.
- **`--user` is required, not defaulted to `admin`**, in both scripts: any MarkLogic user with the admin role works (some sites use a dedicated administrator account). `MARKLOGIC_USER` supplies it when `--user` is not given.
