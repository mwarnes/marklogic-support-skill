# Customer data requests for security and authentication tickets

The **support dump does not carry the security configuration**: users, roles, external security profiles, certificates and the Security database are not in it (`supportdump-anatomy.md`), and the ErrorLog trace lines that show a login step exist only when trace events were switched on. For an LDAP, certificate, OAuth, SAML, HTTPS or Kerberos ticket, ask the customer to collect the data with one of two routes and put the request in "Questions to ask the customer" and `Required-Diagnostics.md`:

| Route | Use when | What it needs |
| --- | --- | --- |
| **A. Gather script** (preferred) | The customer can run Python on any machine that reaches the Management API (port 8002; it need not be a MarkLogic host) | `python3` (standard library), `curl`, `openssl`; a MarkLogic user with the `admin` role; the script `assets/support-scripts/ml-security-gather.py` and `ml-trace-events.py` (master copy and download: https://github.com/mwarnes/mwarnes-marklogic-scripts/tree/main/scripts/Security; hand the customer the skill's copy if they cannot reach GitHub) |
| **B. Management API by hand** | No Python, or change control forbids running a script | `curl` and an administrator login; the calls below; trace events through the Admin UI |

Apply the security incident gate (`security-vulnerability-handling.md`) before asking any customer for logs. Unexpected successful logins, a burst of failed logins from unknown sources or a suspected stolen credential are incident signals, not configuration faults. How to read what comes back: `security-authentication.md`.

Gather facts first (one message, only what is missing): MarkLogic version; scheme and, for OAuth, the flow (Resource server or Authorization code); app server name and group; external security profile name; one failing user and one working user (MarkLogic user name for LDAP, certificate DN or CN, SAML or OAuth login name); the exact HTTP status and any error text the user sees; the time of one failing attempt **in UTC** and the host's time zone; and whether a proxy or load balancer sits in front.

## Route A: gather script

Customer request (replace the `<...>` parts and the area; the per-area additions are listed after it):

> To see how your security is configured and what MarkLogic logged during a failed login, please run our read-only collection script. It changes nothing except that it switches a few trace events on and off. Run it as a MarkLogic user with the `admin` role.
>
> 1. Get `ml-security-gather.py` and `ml-trace-events.py` (we attach them / download them from `<link>`) and put both in one folder. They need `python3`, `curl` and `openssl`. We need this because the support dump does not contain security settings.
> 2. Set the password in the environment so it is never typed on a command line: `export MARKLOGIC_PASS='<password>'`.
> 3. Switch the trace events on: `python3 ml-trace-events.py enable --host <host> --user <admin user> --preset <saml|oauth|ldap|certificate>`. (`certificate` with LDAP groups: run it a second time with `--preset ldap`. The HTTPS area needs no trace events.) Without them the log shows only the final error.
> 4. In the profile set `cache-timeout` to `1` while testing, otherwise a retry within 5 minutes can log nothing. Note the time in UTC (`date -u +%Y-%m-%dT%H:%M:%SZ`).
> 5. Reproduce **one** failing login with `<user>` (a private browser window for SAML and OAuth; `curl -v` for certificates), then, if you have one, a login that works.
> 6. Run the collection: `python3 ml-security-gather.py <area> --host <host> --user <admin user> <area options> --logs --start <UTC time from step 4>`. If the Management API is plain HTTP add `--scheme http`; for a private CA add `--cacert <ca.pem>`.
> 7. Switch the trace events off: `python3 ml-trace-events.py disable --host <host> --user <admin user> --preset <preset>`.
> 8. Open `SUMMARY.md` in the new `<area>-gather-<timestamp>` folder and read the first lines (the conclusion). It contains host names, entity IDs, certificate details and user names; remove anything you do not want to share. Passwords, private keys, client secrets and whole tokens are already removed. Send us the `.zip` next to the folder, and tell us the time zone of each MarkLogic host.

Per-area options (the `<area options>` in step 6; `--external-security` is optional and defaults to every profile of the area):

| Area | Options to add | Also ask for |
| --- | --- | --- |
| `saml` | `--external-security <profile> --user-name <MarkLogic user> --idp-metadata <metadata file or URL>` and, if you can capture one, `--saml-response response.txt` | The IdP's metadata (file or URL); a captured SAMLResponse of the failing login (browser SAML tracer extension; it holds user attributes and stays on the customer's machine, the script never copies it into the zip); the group attribute the IdP sends |
| `oauth` | `--external-security <profile> --token token.txt` (Resource server), `--user-name <user>` | A token that the failing client sent (a bare JWT or an `Authorization: Bearer` line). A live token is a credential: prefer a test user's or an expired one; it stays on the customer's machine and whole JWTs are removed from everything the script writes. For Authorization code add what the browser showed **at the IdP** (the script cannot see the IdP's log) |
| `ldap` | `--external-security <profile> --appserver <app server> --user-name <MarkLogic user>` | The output of the two `ldapwhoami` commands (search account, then user) and the `ldapsearch` that the report prints; the directory's access log for the same second (389-ds buffers it: `nsslapd-accesslog-logbuffering: off` for the test) |
| `certificate` | `--appserver <app server> --client-cert client.pem --client-chain ca-chain.pem` | The **public** certificate only (a file that holds a private key is refused) and its chain; the output of `curl -v --cert client.pem --key client.key --cacert ca.pem https://<host>:<port>/` or `openssl s_client -connect <host>:<port> -cert client.pem -key client.key -CAfile ca.pem` (a rejected handshake leaves nothing in MarkLogic's logs; browsers hide invalid certificates) |
| `https` | `--appserver <app server> --server-ca <ca.pem> --probe-host <name clients use>` | The client's exact error and the name or address the client connects to; no trace events needed |

Engineer notes:
- Only `--host` and `--user` are required; anything left out is listed under **Not collected** in `SUMMARY.md` with the option that adds it, and the conclusion says how many parts were not collected. A verdict covers only what was collected: re-request the missing part, do not conclude without it.
- The script is read-only; `ml-trace-events.py` adds events to the group and `disable` removes only the ones it added (state in `.ml-trace-events-state.json` in the current directory). The group defaults to `Default`; run it once per group (`--group`) if the app servers are in other groups.
- It probes the IdP, directory or app server **from the machine that runs it** (`--no-probe` disables that). A probe from a laptop proves little about the MarkLogic hosts: for a name-resolution or TLS failure also ask for the same `openssl s_client` or `curl` from a MarkLogic host.
- `--start` and `--end` are UTC; logs are in each host's local time zone, so widen the window when a host is not on UTC. The ErrorLog has no app server name: reproduce one login at a time.
- Verified on MarkLogic 11.3.7 and 12.1.0 by the maintainer; `--help` of the script is the authority for options. Details of the areas and what each checks: `assets/support-scripts/README.md`.
- The script's output folder holds `SUMMARY.md` plus the raw JSON of each call; read it with the "Security gather mode" in `SKILL.md`.

## Route B: Management API by hand

Customer request:

> Please run the following calls as an administrator and save each result to the file named. `curl -u <admin user>` asks for the password so it is not on the command line. Use `http` instead of `https` if the Management API is not TLS-protected, and `--cacert <ca.pem>` for a private CA. Replace `<...>`.
>
> 1. Cluster and version: `curl --anyauth -u <user> "https://<host>:8002/manage/v2?format=json" > cluster.json`
> 2. The external security profiles: `curl --anyauth -u <user> "https://<host>:8002/manage/v2/external-security?format=json" > external-security-list.json`, then for the profile in question `curl --anyauth -u <user> "https://<host>:8002/manage/v2/external-security/<profile>/properties?format=json" > profile.json`.
> 3. The app server and what it is bound to: `curl --anyauth -u <user> "https://<host>:8002/manage/v2/servers/<app server>/properties?group-id=<group>&format=json" > appserver.json` (the `external-security`, `authentication`, `internal-security`, `ssl-*` properties are the ones we need).
> 4. The user and the roles involved: `.../manage/v2/users/<user>/properties?format=json > user.json` and, for each role the user should receive, `.../manage/v2/roles/<role>/properties?format=json > role-<role>.json` (we need the `external-names`).
> 5. For HTTPS or certificate problems: `.../manage/v2/certificate-templates/<template>?format=json`, `.../manage/v2/certificates?format=json`, `.../manage/v2/certificate-authorities?format=json` (and `.../<id>` of the entries involved).
> 6. Trace events: in the Admin Interface open **Groups › (the app server's group) › Diagnostics**, enable the trace events listed for the scheme below, **Save**, and tell us when you turn them off again. (Do not set them with a hand-written `PUT` to the group properties: it replaces the whole list.)
> 7. Reproduce one failing login and note the time in UTC. Then save the ErrorLog for that window: `curl --anyauth -u <user> "https://<host>:8002/manage/v2/logs?filename=ErrorLog.txt&host=<host>&format=text&start=<UTC start>&end=<UTC end>" > ErrorLog-<host>.txt` (for each host that served the request) and the app server's access log: `.../manage/v2/logs?filename=<port>_AccessLog.txt&host=<host>&format=text > AccessLog.txt` (it cannot be limited by time, so it may be large: send the last part).
> 8. **Before sending, open every file and delete the value of any key whose name contains `password`, `secret`, `private-key` or `passphrase`.** Never send a private key or a live access token.
>
> Trace events: LDAP `External Authenticate`, `LDAP`, `LDAP Search`; certificate `External Authenticate` (add the LDAP events for LDAP groups); OAuth `OAuth`, `OAuth Status`, `OAuth Communications`, `OAuth JSON Processing`, `External Authenticate`; SAML `SAML`, `SAML Response`, `External Authenticate`.

Engineer notes:
- Endpoints verified by the maintainer on 11.3.7 and 12.1.0 (`assets/support-scripts/README.md`): lists are read from the `list-item` entries (other `nameref` values point at related objects); the certificate template `/properties` call returns HTTP 400 on MarkLogic 11, the plain template call works on both; `GET /manage/v2/certificates/<id>` and `/certificate-authorities/<id>` return parsed fields (`temporary`, `template-id`, serial, validity, subject and issuer) and no PEM; the client CA list of an app server is not available through the Management API (the `ssl-client-certificate-authority` ids are).
- Whether a GET returns the LDAP bind password in clear is `[unverified — confirm]`: the gather script removes it, so tell the customer to redact by hand (step 8). The OAuth client secret is write-only and never shown; the SAML SP private key is returned encrypted.
- The manual route gives the data but none of the checks. Do the comparisons yourself with `security-authentication.md` (issuer vs token, DN vs external name, group value vs role external name) and ask for the client-side commands in Route A.
- `GET /manage/v2/logs` with `start`/`end` works for the ErrorLog; the access log returns `MANAGE-CANNOTSEARCH` with them, so read it whole. Loose ErrorLog files can also go through Log mode (`analyse_logs.py`), which does not understand the SAML, OAuth or LDAP trace lines: grep `events.jsonl` or the split log for `External Authenticate`, `Saml Response`, `OAuth Status`.

## Kerberos (no gather area)

The script does not read Kerberos settings, and the maintainer's Kerberos notes are untested on MarkLogic 11 and 12, so every item here is `[unverified — confirm]`. Customer request:

> 1. Which MarkLogic version, which app server and which external security profile (`GET /manage/v2/external-security/<profile>/properties?format=json`, Route B step 2) is used? What exact name do users type in the browser, and does a load balancer sit in front?
> 2. On **each** MarkLogic host that can serve the request, in the host's MarkLogic data directory: `ls -l services.keytab` and `klist -kte services.keytab` (principals, key versions and encryption types). We need this to see whether the keytab exists, is readable by the MarkLogic account and holds the principal the browser asks for.
> 3. From a client: `klist` after the failed attempt, and `kvno HTTP/<the name in the URL>@<REALM>` (the key version the KDC issues; it must match the keytab).
> 4. On each MarkLogic host: `date -u`, `timedatectl status` (time skew is a common cause); and `nc -zv <kdc> 88` and `nc -zv <kdc> 464`.
> 5. The ErrorLog for one failing attempt (Route B step 7); mask keys, tickets and passwords first. Never send the keytab itself.

Engineer notes: the keytab is a credential, never ask for it. The Kerberos library and KDC wording (`KRB_AP_ERR_SKEW`, `KRB_AP_ERR_BADKEYVER`) is not necessarily MarkLogic's own message. Ask the customer to separate "no ticket from the browser", "ticket issued but rejected" and "authenticated but denied" (`security-authentication.md`, Kerberos rows).

## Before you send and after it arrives

- Tell the customer the report holds host names, entity IDs, certificate details and user names; they review it. Private keys, passwords, client secrets, keytabs and live tokens are never requested.
- Record the request as a `Required-Diagnostics.md` entry; when the zip arrives, add a `**Status:** Received ...` line to that entry (`ticket-auditing.md`). Keep any customer data under the ticket directory, in its own folder, and do not run anything from inside it.
- A ticket that is really a vulnerability or incident follows `security-vulnerability-handling.md` instead.
