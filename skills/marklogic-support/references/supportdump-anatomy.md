# Support dump anatomy and how to use the extracted artefacts

## Layout of a cluster-scope support dump

Sections are delimited by a `=====` line, a title line, another `=====` line (rules may be indented).
`%%%%` lines delimit header blocks.

1. **Cluster header** (`Report Time/Type/Scope/Version/Destination/Host`), then cluster-wide status:
   - `App Server Status` — one `<server-status>` per app server × host (`Group: …, Appserver: …, Host: …` line precedes each).
   - `Database Topology` — text: per database its forests, security/schemas/triggers DB names, status.
   - `Forest Status` — one sub-section per forest (title = forest name) holding `<forest-status>` (state, host-id, disk-size MB,
     memory-size, journals-size, device-space = free MB on the device, stands, reindexing, rebalancing, document-count) and
     `<forest-counts>`.
   - Trigger Definitions / CPF Domains / CPF Pipelines / FlexRep Domains / SQL Schemas / SQL Views / XML Schemas — per-database inventories.
2. **One per-host report per host**, opened by a `%%%%` block with `Hostname:` / `Product Version:`:
   - `Host Status` — `<host-status>`: version, os-version, cpus, memory-system-total (MB), memory-system-free, memory-process-rss,
     memory-size, data-dir-space, cache sizes in use.
   - `Configuration` — `server.xml`, `groups.xml`, `databases.xml`, `assignments.xml`, `hosts.xml`, `clusters.xml`, `keystore.xml`,
     `kms.xml`; each as `=== <file> ===` then `=== Validation results: OK ===` then the XML. The set is cluster-wide and should be
     identical on every host (only the `timestamp` attribute may differ).
   - `Log Files` — one section per log; title is the path (`/var/opt/MarkLogic/Logs/<name>` on the report host,
     `file://<host>/var/opt/MarkLogic/Logs/<name>` elsewhere). Kinds: `ErrorLog.txt`, `<port>_ErrorLog.txt`, `<port>_AccessLog.txt`,
     `<port>_RequestLog.txt`, `TaskServer_ErrorLog.txt`, `TaskServer_RequestLog.txt`, `AuditLog.txt`, `CrashLog.txt`. Most per-port
     logs are 1-line placeholders.

## How the configuration files join (all by numeric IDs)

| File | Key | Points to |
| --- | --- | --- |
| `clusters.xml` | cluster-id / cluster-name, effective-version | `bootstrap-hosts/bootstrap-host` → host-id; `foreign-clusters` |
| `hosts.xml` | host-id → host-name, zone, bind-port | `group` → group-id (**this is the host list**) |
| `groups.xml` | group-id → group-name, cache sizes, failover-enable, host-timeout | `http/xdbc/odbc/webdav-servers/*`: port, `database` → database-id, `modules` → database-id (0 = filesystem), authentication, `default-user` → user-id, root |
| `databases.xml` | database-id → database-name, index settings, reindexer/rebalancer, directory-creation, locking | `security/schema/triggers-database` → database-id; `forests/forest-id` → forest-id |
| `assignments.xml` | forest-id → forest-name, data-directory, failover-enable | `host` → host-id; `forest-replicas/forest-replica` → forest-id; `failover-hosts/failover-host` → host-id |
| `server.xml` | this host's host-id, licensee, license-key | — |
| `keystore.xml` | data/config/logs-encryption | — |

Users and roles live in the Security database and are **not** in the dump — `default-user` cannot be resolved to a name.

## Artefacts written by `scripts/parse_dump.py <dump> [--out DIR]` (default `dump-analysis/<dump-stem>/`)

| Path | Use it for |
| --- | --- |
| `summary.md` | Read first: cluster → hosts (CPU/RAM/free disk) → groups (caches) → app servers → databases → forests per host |
| `findings.md` | Deterministic checks, ranked high/medium/low; each row names the phase-1 reference file and Mistake row to apply |
| `topology.json` | Full ID-resolved model when a question needs a value the summary omits (`jq`/python, do not paste whole) |
| `config/<host>/*.xml` | Raw configuration when a finding needs the exact setting; hosts should be identical |
| `status/*.txt` | Raw cluster status sections (App-Server-Status, Forest-Status, Database-Topology, Host-Status…) |
| `logs/INVENTORY.md`, `logs/<host>/<name>` | Split logs; placeholders skipped |
| `logs/<host>/ERRORLOG-SUMMARY.md` | Levels, top error codes with first/last seen, restarts, time span — read before opening a raw ErrorLog |

## Working rules

- Never read the raw dump in the agent; always run the script and work from the artefacts.
- A finding is a hypothesis: confirm it with the evidence column, then explain using the referenced reference row.
- Checks that could not evaluate (missing Host Status data) appear as `low` "cannot evaluate" findings — say so, don't guess.
- Things the dump cannot tell you: user/role privileges, application code, network/firewall state, historical load.
