# MarkLogic logs — formats, what the events mean, and how to read the analysis

## Formats

| Log | Where | Line format | Notes |
| --- | --- | --- | --- |
| `ErrorLog.txt`, rotated `ErrorLog_1.txt`… | `/var/opt/MarkLogic/Logs/` | `YYYY-MM-DD hh:mm:ss.fff Level: message` | Levels Debug…Emergency; stack traces are continuation lines. `_1` = previous day |
| `<port>_ErrorLog.txt`, `TaskServer_ErrorLog.txt` | same | same | per app server / task server |
| `/var/log/messages` (often supplied as `messages_<host>`) | OS syslog | `Mon DD hh:mm:ss HOST prog[pid]: message` | **no year, no level**; MarkLogic forwards its ErrorLog here when configured. Also kernel (OOM-killer, I/O errors), systemd (`Starting/Stopped MarkLogic Server`), chronyd/ntpd |
| `<port>_AccessLog.txt` | same | Common Log Format | one line per HTTP request: client, user, time, request, status |
| `AuditLog.txt` | same | `ts event=…; uri=…; database=…; success=…; user=…; roles=…` | only when auditing is enabled |
| `<port>_RequestLog.txt` | same | JSON per request | not analysed |

Time zones: ErrorLog uses the server's local time; syslog uses the OS local time (often the same, not always). The
analysis never converts — compare spans in `INVENTORY.md` before correlating across sources.

## Event catalogue → what it usually means → where to read

| kind | typical lines | implication | reference row |
| --- | --- | --- | --- |
| restart / shutdown | `Starting MarkLogic Server`, systemd Start/Stop | process restarted — look 0–30 min earlier for the cause (memory, storage, kernel OOM) | cluster-hosts-groups.md |
| quorum | `Detected quorum (N online…)`, `XDMP-NOQUORUM` | cluster membership changed; NOQUORUM = forests unavailable | cluster-hosts-groups.md — even host count |
| host-state | `XDMP-HOSTOFFLINE`, `Disconnecting from domestic host` | a host was declared down by peers | cluster-hosts-groups.md — XDQP ports / host timeout |
| xdqp | `Restarting XDQPServer`, XDQP timeouts, `XDMP-XDQPVER` | inter-host link problems: network, host timeout, version mismatch | cluster-hosts-groups.md |
| clock-skew | `XDMP-CLOCKSKEW … skewed by N seconds` | NTP broken or a host paused (VM stall / memory thrash) | cluster-hosts-groups.md — clock skew |
| memory | `Memory low: anon+swap+file=N%phys`, `XDMP-MEMCANCELED`, kernel `Out of memory: Killed process (MarkLogic)`, `Linux Huge Pages: detected 0` | caches + range indexes exceed RAM; OOM-kill causes restarts | memory-and-os.md |
| forest-mount | `Mounted/Unmounted forest`, `XDMP-FORESTMNT … not mounted: disconnected`, `Forest X state changed` | forests moving/unavailable; after a restart this is normal recovery | databases-forests.md, ha-backup-failover.md |
| failover | `failover`, `open replica`, `sync replicating` | replica took over / is catching up | ha-backup-failover.md |
| storage | `Detecting indexes … slow … storage problems`, `Slow utime/fsync`, `XDMP-FORESTNOSPACE`, kernel I/O errors | disk latency or full; the single most common root cause behind restarts and timeouts | databases-forests.md — disk headroom |
| merge-reindex | `Merged N MB`, `Reindexing` | normal; heavy volume during business hours = throttle/scheduling issue | databases-forests.md — reindexer throttle |
| backup | `backup to`, `Restoring` | scheduled jobs; failures show as Error lines | ha-backup-failover.md |
| security | `SEC-*`, `XDMP-AUTH*`, `Invalid login` | permission/auth failures — pair with AUDIT.md | security.md |
| appserver | `SVC-SOCBIND` (port in use), `SVC-SOCACC` (client disconnects, often load-balancer/TLS noise), `XDMP-EXTIME` | port conflicts or timeouts; SOCACC at high volume is usually health-check noise | app-servers.md |
| error-line | any other Critical/Error/Alert/Emergency | read the code; look it up in the references' `How to confirm` cells | by code |

## Typical causal chains (read the timeline top-down)

- `memory` (Memory low ↑) → `clock-skew` (host stalls) → `xdqp` restarts / `XDMP-FORESTMNT` on peers → `storage` ("Detecting indexes is slow") → `restart` (OOM-kill or manual) → `forest-mount` × many → `quorum` → `merge-reindex` catch-up. Root cause: memory (group caches vs RAM, forests per host) or storage latency; the restart is the symptom.
- `storage` bursts without memory events → disk/SAN latency or space; check `disk-headroom` in the dump findings.
- `xdqp`/`host-state` on one host only, no memory/storage → network/firewall between hosts or host timeout.
- `security`/AUDIT `success=false` bursts → credential or role misconfiguration, or an attack.

## Artefacts of `scripts/analyse_logs.py PATH... [--out DIR] [--host NAME] [--topology topology.json]`

| Path | Use |
| --- | --- |
| `INVENTORY.md` | what was analysed: file → kind, host, lines, span, notes (`year inferred`, `unknown` host, `unclassified`); syslog programs table |
| `TIMELINE.md` | merged incident timeline, catalogued events only, repeats collapsed `×N`; ≤ 500 rows (low-severity dropped first) |
| `hosts/<host>/TIMELINE.md` | same per host |
| `PATTERNS.md` | per host/source: levels, top codes with first/last/sample, hourly **burst** tables |
| `ACCESS.md` / `AUDIT.md` | only when such logs exist; open only for access/availability or security tickets |
| `events.jsonl` | every event incl. uncatalogued ones (`kind: null`) — grep it for a code or time window |

`--host` forces the host for loose files whose name carries no host (e.g. a bare `ErrorLog_1.txt`); otherwise they appear as `unknown`.
`--topology` (auto-detected under `dump-analysis/<x>/`) annotates forest names with their database and flags hosts not in the cluster.
