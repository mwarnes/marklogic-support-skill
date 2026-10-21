---
name: marklogic-support
description: Triages MarkLogic support tickets across configuration (clusters, hosts, groups, forests, databases, app servers, security, memory/caches, backup/failover), monitoring, query performance/tuning, DR/scaling, server-side code review (XQuery/JS/REST extensions), and client-side tooling (XCC, Java Client API, mlcp, ml-gradle, CoRB2), from distilled reference notes. Use for any MarkLogic ticket, symptom, error code, or admin question. MarkLogic 11/12. Also splits and analyses support dumps (config/status/logs, findings) and ErrorLog/var-log-messages into incident timelines. Also gates security-incident tickets and applies the organisation's security-vulnerability process.
---

# MarkLogic Support (Phase 1: configuration issues)

## Always first

1. Read `references/architecture.md` (short) so the component model is in context.
2. Classify the input:
   - Ticket text / symptom / error code → **Triage mode**
   - Direct question → **Q&A mode**
   - A support dump (a file path, or pasted text starting `Report Time:`) → **Dump mode**
   - Log files (ErrorLog*, messages*, AccessLog, AuditLog — loose or in a dump analysis) → **Log mode**
   - Linux SAR/sysstat output (a `sar -A` text file, a binary `sa##` file, or a folder of them) → **SAR mode**
   - Unclear → ask which.
3. **Security check (before any analysis).** Read `references/security-vulnerability-handling.md`
   ("Detect") whenever the ticket, a pasted symptom, a dump or a log request mentions a CVE/CVSS,
   scanner output, a vulnerability or exploit, or a security incident, security event, malware, virus,
   ransomware, compromise or intrusion.
   An incident stops work at the **incident gate** described there — analyse no customer-supplied dump
   or log and draft no log request until the engineer clears it. The gate stays open for the whole
   ticket, in every mode and in later sessions, until `audit-trail/Timeline.md` contains a "Security
   incident gate cleared" line after the "Security incident gate raised" line. Before running
   `parse_dump.py`, `analyse_logs.py` or `analyse_sar.py` or drafting a log request, check `Timeline.md` for a "Security
   incident gate raised" line without a later "Security incident gate cleared" line and, if open,
   stop. A vulnerability prints the banner and checklist first. Never write the word "breach".

Scripts are run with `python3`; on Windows use `python` or `py -3` if `python3` is not available.

## Triage mode

1. Extract facts from the ticket (state what is missing): MarkLogic version; cluster size / host count; what changed recently (upgrade, new host, index change, config change); exact error text / codes; affected component (host, forest, database, app server, security).
2. Pick 1–2 reference files from the routing table and read them fully.
3. Answer in exactly this format:

   **Likely causes (ranked)** — each with the confirming check that would prove it; mark each as `config error` or `possible bug / capacity limit`.
   **Questions to ask the customer** — only those whose answer changes the ranking.
   **What to check** — for each: Admin UI path, REST Management API (`GET /manage/v2/...`), or XQuery (`xdmp:*`, `admin:*`) — whichever the reference gives.
   **Best-practice recommendation** — the fix, plus how to prevent recurrence.
   **Doc links** — from the reference's `## Sources` / `references/sources.md`.

For a security vulnerability ticket, print the banner and checklist from `references/security-vulnerability-handling.md` first, then this format.

For a performance or resource-pressure ticket with no host-level data (no SAR, iostat, vmstat or mpstat output), put a request from `references/performance-data-requests.md` in "Questions to ask the customer" — the SAR export or live capture, the host metrics, and, only when the customer runs on a cloud provider (for example AWS), its cloud signals. Ask for kernel/OOM messages on memory symptoms, and `pmap` only for runaway memory growth. For a hang, an unresponsive period or a query behaving unexpectedly, ask for the pstack movie; for sustained high CPU, or when pausing the process is a concern, ask for perf instead — pstack pauses the MarkLogic process while it records the threads, perf only samples it (both procedures are in `references/performance-data-requests.md`; the customer script is `assets/support-scripts/pstack.sh`). Never ask for either from a customer who mentioned a security incident until the incident gate is cleared. When pstack output (a pstack.log or a pstack movie zip) is supplied, read `references/pstack-analysis.md` and analyse it by hand — there is no analysis script yet — after the security incident gate check. For a stuck or slow request, also ask for the request/server status capture (`references/performance-data-requests.md`) before anything is cancelled. For an incident that has already passed, ask for the Monitoring History data instead: check Telemetry, otherwise the Meters export (`references/performance-data-requests.md`).

Rules: never assert a root cause without at least one confirming check. Quote error codes exactly. If the reference row is marked `[unverified — confirm]`, say so.

Then update the audit trail per the **Audit trail** section below.

## Q&A mode

Answer from the references; cite the reference file and the source URL. If the answer is version-dependent, say which version each statement applies to. If the references do not cover it, say so and point to the closest `references/sources.md` link rather than guessing.

## Dump mode

Check the security incident gate first (Always first, step 3).

1. If the dump was pasted, save it to a file first. Run `scripts/parse_dump.py <dump> --out dump-analysis/<dump-basename>`, resolving `scripts/` relative to THIS skill's own directory (the directory this SKILL.md lives in — not the project's working directory). If unsure of the skill directory's absolute path, `ls` around this file first, then invoke e.g. `python3 /abs/path/to/this/skill/scripts/parse_dump.py <dump> --out dump-analysis/<dump-basename>`. Never guess or hardcode a path from a previous project.
2. Read `references/supportdump-anatomy.md`, then `<out>/summary.md` and `<out>/findings.md`. Do not read the raw dump.
2b. If `<out>/logs/` exists, also run `scripts/analyse_logs.py <out>/logs --out <out>/log-analysis` (same skill-relative resolution as step 1) and read its `TIMELINE.md` and `PATTERNS.md` — the dump's own logs cover the report day.
3. Output, in this order:
   **Cluster overview** — 5–10 lines from `summary.md`: version, hosts (CPU/RAM), groups, app servers, databases/forests, replicas, encryption.
   Then the Triage-mode format (Likely causes ranked · Questions to ask · What to check · Best-practice recommendation · Doc links), where each cause comes from a finding: read the referenced phase-1 file's row, state the finding's evidence, and mark `config error` / `possible bug / capacity limit`. Group repeated findings (e.g. 40 forests without replicas) into one cause listing the affected databases.
4. If the engineer also gave a ticket symptom, rank findings that explain the symptom first and say which findings are unrelated.
5. For detail beyond the summary, read `topology.json`, the specific `config/<host>/*.xml`, or `logs/<host>/ERRORLOG-SUMMARY.md`. Open a raw log only for a specific timestamp/code.
6. Then update the audit trail per the **Audit trail** section below.

## Log mode

Check the security incident gate first (Always first, step 3).

1. Run `scripts/analyse_logs.py <files or dirs> --out log-analysis/<name>`, resolving `scripts/` relative to THIS skill's own directory (see Dump mode step 1 for how to find it) — add `--host <host>` for a loose ErrorLog whose host you know; add `--topology dump-analysis/<x>/topology.json` when a dump analysis exists. Never read a raw log wholesale.
2. Read `references/log-anatomy.md`, then `<out>/INVENTORY.md`, `<out>/TIMELINE.md`, `<out>/PATTERNS.md`. Open `ACCESS.md` only for access/availability tickets and `AUDIT.md` only for security tickets. For a specific code or minute, grep `events.jsonl` or the split log — never paste whole logs.
3. Output: **Incident timeline** — the 5–15 key events in order (time as written, host, kind, one-line meaning), the causal chain you infer, and what the logs cannot show; then the Triage-mode format. Distinguish "symptom" events (restart, forest mounts) from "cause" events (memory, storage, network) explicitly.
4. If a dump analysis exists, cross-reference its `findings.md` (e.g. cache-vs-ram ↔ Memory low; failover-no-replica ↔ database unavailable during restart).
5. Then update the audit trail per the **Audit trail** section below.

## SAR mode

Check the security incident gate first (Always first, step 3): SAR output is a customer-supplied file.

1. Run `scripts/analyse_sar.py <files or dirs> --out sar-analysis/<name>`, resolving `scripts/` relative to THIS skill's own directory (see Dump mode step 1). Never read a raw SAR file wholesale. If it reports a binary `sa##` file it cannot convert, ask the customer for text output using the "SAR export" request in `references/performance-data-requests.md`.
2. Read `references/sar-analysis.md`, then `<out>/SUMMARY.md`. Open `<out>/series-<host>.csv` only for a specific window and `findings.json` for exact values.
3. Output: **Host timeline** — per host the window, interval, restarts and gaps (SAR not collecting); **Findings** — each ranked finding (likely causes first) with what it means for MarkLogic and the confirming check from `sar-analysis.md`; then the Triage-mode format. Align SAR times with the ErrorLog timezone before correlating (Log mode `TIMELINE.md`), and say what SAR cannot show.
4. If the data does not cover the incident window, or lacks a section a finding needs (for example no `-d` disk data), say so and request it from `references/performance-data-requests.md`.
5. Then update the audit trail per the **Audit trail** section below; a data request is a `Required-Diagnostics.md` entry.

## Audit trail

If `audit-trail/` exists in the current working directory, or in the ticket directory set up by the `ticket` skill earlier in this session (`<project root>/<ticket>/audit-trail/`) (created by `/ticket`), read
`references/ticket-auditing.md` once per session, then after producing output in Triage, Dump,
Log, or SAR mode (never Q&A mode — a one-off question is not ticket work):

- Append one `Timeline.md` line for what just happened.
- A new ranked cause → append a `Problems.md` entry, status `Open`, unless evidence already in
  hand confirms or rules it out.
- A new "Questions to ask the customer" → append a `Required-Diagnostics.md` entry,
  Salesforce-paste-ready.
- Data just supplied answers an existing diagnostic request → find that request by its heading,
  append a `**Status:** Received ...` line (never edit or delete the original ask).
- Real diagnostic reasoning (dump/log correlation, evidence review) → an `Analysis.md` entry,
  stage-tagged (`[Identification]`/`[Diagnosis]`/`[Escalation]`/`[Resolution]`/`[Closure]`), citing
  the `Problems.md`/`Required-Diagnostics.md` entry numbers it relates to.

On a security vulnerability or incident ticket follow "Audit trail on security tickets" in
`references/security-vulnerability-handling.md`: record the process steps and `Details recorded in
<secure location>`, never exploit specifics or the word "breach".

**Never auto-write without the engineer's explicit go-ahead in the conversation:** a `Problems.md`
entry moving to `Confirmed`, `Root-Cause.md` itself, an `[Escalation]` entry, or a `[Closure]`
entry. These are assertions, not triage output — propose them, then write only once the engineer
confirms (e.g. "confirmed", "write up root cause", "we escalated to X", "customer accepted, close
it"). If `audit-trail/` exists in neither place, skip all of this silently.

**After a confirmed `[Closure]` entry is written**, offer once — in one sentence, no other action —
to draft a KCS article with `/kcs` (or `/kcs <ticket>` in a later session). Skip the offer if
`<ticket>/kcs/` already holds an article for this ticket, or the engineer has declined it.

## KCS articles

On `/kcs` (the `kcs` skill) or a request to write a KCS article for a finished ticket, read
`references/kcs-writing.md` and write from the ticket's `audit-trail/`; render with
`scripts/kcs_render.py`. Never in Q&A mode without a ticket.

On `/kcs-review` (the `kcs-review` skill) or a request to review someone else's KCS article,
read `references/kcs-writing.md` ("Reviewing an article") and import/render with
`scripts/kcs_render.py` (`--to-md`, `--target`). No ticket is involved.

## Routing table (symptom / keyword → reference)

| If the ticket mentions… | Read |
| --- | --- |
| CVE, CVSS, vulnerability, exploit, scanner output, security scan, security incident, security event, malware, virus, ransomware, compromise, intrusion | `references/security-vulnerability-handling.md` (read first, before any other reference) |
| meters export, monitoring history export, telemetry, stuck query, request-status, sar, sysstat, sadf, iostat, vmstat, mpstat, pidstat, %iowait, await, %util, run queue, load average, %steal, swap in/out, slow disk, OOM killer, performance data, pstack, perf, stack trace, hang, unresponsive, high CPU | `references/sar-analysis.md`, `references/performance-data-requests.md` and `references/pstack-analysis.md` |
| quorum, host offline, XDQP, XDMP-HOSTOFFLINE, join/leave cluster, hostname, group, upgrade/effective version, NTP/clock | `references/cluster-hosts-groups.md` |
| forest, stand, merge, disk space, XDMP-FORESTNOSPACE, reindex, index, rebalancer, assignment policy, directory creation, fragment, locking | `references/databases-forests.md` |
| port, app server, HTTP/XDBC/ODBC/WebDAV, modules, XDMP-MODNOTFOUND, SVC-SOCBIND, timeout, XDMP-EXTIME, threads, authentication (app-server level), SSL/TLS, log level, 8000/8001/8002 | `references/app-servers.md` |
| permissions, role, privilege, amp, SEC-*, LDAP/Kerberos/SAML, admin password, audit, encryption/keystore | `references/security.md` |
| failover, replica, backup, restore, XDMP-FORESTNOT, journal archiving, point-in-time, scheduled task | `references/ha-backup-failover.md` |
| memory, OOM, XDMP-MEMCANCELED, swap, huge pages, cache (list / compressed tree / expanded tree / triple), CACHEFULL, ulimit, XDMP-TOOMANYOPENFILES, I/O scheduler | `references/memory-and-os.md` |
| monitoring dashboard, Meters database, ops director, monitoring history, view=status, alerting, baseline, historical data, manage-user, Performance Metering Enabled, xdmp:server-status, xdmp:request-status, xdmp:host-status, status screen, log disk space | `references/monitoring.md` |
| slow query, cts:search, filtered/unfiltered search, range index, positions index, lexicon, query-meters, query-trace, profiler, XDMP-TREECACHEFULL | `references/performance-tuning.md` |
| disaster recovery, database replication, flexible replication, foreign cluster, non-blocking timestamp, rebalancer, assignment policy, scale out, add host, retire forest | `references/dr-scaling.md` |
| review this code, REST extension, resource extension, fn:error/fn.error, xdmp:eval/xdmp:invoke in code, hardcoded credentials, code review | `references/app-code-review.md` |
| XCC, ContentSource, DatabaseClient, Java Client API, DMSDK, mlcp, -fastload, batch size, transaction size, ml-gradle, gradle.properties, mlDeploy, CoRB, CoRB2, URIS-MODULE, PROCESS-MODULE, DISK-QUEUE, FAIL-ON-ERROR | `references/client-integration.md` |
| architecture / "how does X relate to Y" | `references/architecture.md` only |
| support dump, `Report Time:`, `databases.xml`, `hosts.xml`, "analyse this dump" | run `scripts/parse_dump.py`, then `references/supportdump-anatomy.md` |
| ErrorLog, messages, syslog, "log file", "what happened at", "restarted at", OOM | Log mode → references/log-anatomy.md |

Multiple matches → read both (max 2). No match → ask one clarifying question, then re-route.

## Out of scope

Access/request-log analytics, correlating log events with configuration, comparing two dumps, Security-database contents (users/roles), executing or testing customer code (review is static-checklist only, not execution), anything requiring live cluster access. Say so explicitly when asked.
