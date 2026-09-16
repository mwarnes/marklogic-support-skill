---
name: marklogic-support
description: Triages MarkLogic support tickets across configuration (clusters, hosts, groups, forests, databases, app servers, security, memory/caches, backup/failover), monitoring, query performance/tuning, DR/scaling, server-side code review (XQuery/JS/REST extensions), and client-side tooling (XCC, Java Client API, mlcp, ml-gradle, CoRB2), from distilled reference notes. Use for any MarkLogic ticket, symptom, error code, or admin question. MarkLogic 11/12. Also splits and analyses support dumps (config/status/logs, findings) and ErrorLog/var-log-messages into incident timelines.
---

# MarkLogic Support (Phase 1: configuration issues)

## Always first

1. Read `references/architecture.md` (short) so the component model is in context.
2. Classify the input:
   - Ticket text / symptom / error code → **Triage mode**
   - Direct question → **Q&A mode**
   - A support dump (a file path, or pasted text starting `Report Time:`) → **Dump mode**
   - Log files (ErrorLog*, messages*, AccessLog, AuditLog — loose or in a dump analysis) → **Log mode**
   - Unclear → ask which.

## Triage mode

1. Extract facts from the ticket (state what is missing): MarkLogic version; cluster size / host count; what changed recently (upgrade, new host, index change, config change); exact error text / codes; affected component (host, forest, database, app server, security).
2. Pick 1–2 reference files from the routing table and read them fully.
3. Answer in exactly this format:

   **Likely causes (ranked)** — each with the confirming check that would prove it; mark each as `config error` or `possible bug / capacity limit`.
   **Questions to ask the customer** — only those whose answer changes the ranking.
   **What to check** — for each: Admin UI path, REST Management API (`GET /manage/v2/...`), or XQuery (`xdmp:*`, `admin:*`) — whichever the reference gives.
   **Best-practice recommendation** — the fix, plus how to prevent recurrence.
   **Doc links** — from the reference's `## Sources` / `references/sources.md`.

Rules: never assert a root cause without at least one confirming check. Quote error codes exactly. If the reference row is marked `[unverified — confirm]`, say so.

Then update the audit trail per the **Audit trail** section below.

## Q&A mode

Answer from the references; cite the reference file and the source URL. If the answer is version-dependent, say which version each statement applies to. If the references do not cover it, say so and point to the closest `references/sources.md` link rather than guessing.

## Dump mode

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

1. Run `scripts/analyse_logs.py <files or dirs> --out log-analysis/<name>`, resolving `scripts/` relative to THIS skill's own directory (see Dump mode step 1 for how to find it) — add `--host <host>` for a loose ErrorLog whose host you know; add `--topology dump-analysis/<x>/topology.json` when a dump analysis exists. Never read a raw log wholesale.
2. Read `references/log-anatomy.md`, then `<out>/INVENTORY.md`, `<out>/TIMELINE.md`, `<out>/PATTERNS.md`. Open `ACCESS.md` only for access/availability tickets and `AUDIT.md` only for security tickets. For a specific code or minute, grep `events.jsonl` or the split log — never paste whole logs.
3. Output: **Incident timeline** — the 5–15 key events in order (time as written, host, kind, one-line meaning), the causal chain you infer, and what the logs cannot show; then the Triage-mode format. Distinguish "symptom" events (restart, forest mounts) from "cause" events (memory, storage, network) explicitly.
4. If a dump analysis exists, cross-reference its `findings.md` (e.g. cache-vs-ram ↔ Memory low; failover-no-replica ↔ database unavailable during restart).
5. Then update the audit trail per the **Audit trail** section below.

## Audit trail

If `audit-trail/` exists in the current working directory (created by `/ticket`), read
`references/ticket-auditing.md` once per session, then after producing output in Triage, Dump, or
Log mode (never Q&A mode — a one-off question is not ticket work):

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

**Never auto-write without the engineer's explicit go-ahead in the conversation:** a `Problems.md`
entry moving to `Confirmed`, `Root-Cause.md` itself, an `[Escalation]` entry, or a `[Closure]`
entry. These are assertions, not triage output — propose them, then write only once the engineer
confirms (e.g. "confirmed", "write up root cause", "we escalated to X", "customer accepted, close
it"). If `audit-trail/` does not exist, skip all of this silently.

## Routing table (symptom / keyword → reference)

| If the ticket mentions… | Read |
| --- | --- |
| quorum, host offline, XDQP, XDMP-HOSTOFFLINE, join/leave cluster, hostname, group, upgrade/effective version, NTP/clock | `references/cluster-hosts-groups.md` |
| forest, stand, merge, disk space, XDMP-FORESTNOSPACE, reindex, index, rebalancer, assignment policy, directory creation, fragment, locking | `references/databases-forests.md` |
| port, app server, HTTP/XDBC/ODBC/WebDAV, modules, XDMP-MODNOTFOUND, SVC-SOCBIND, timeout, XDMP-EXTIME, threads, authentication (app-server level), SSL/TLS, log level, 8000/8001/8002 | `references/app-servers.md` |
| permissions, role, privilege, amp, SEC-*, LDAP/Kerberos/SAML, admin password, audit, encryption/keystore | `references/security.md` |
| failover, replica, backup, restore, XDMP-FORESTNOT, journal archiving, point-in-time, scheduled task | `references/ha-backup-failover.md` |
| memory, OOM, XDMP-MEMCANCELED, swap, huge pages, cache (list / compressed tree / expanded tree / triple), CACHEFULL, ulimit, XDMP-TOOMANYOPENFILES, I/O scheduler | `references/memory-and-os.md` |
| monitoring dashboard, Meters database, ops director, monitoring history, view=status, alerting, baseline, historical data, manage-user, Performance Metering Enabled | `references/monitoring.md` |
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
