# Monitoring — real-time dashboard, historical data, and external integration

## Concepts

- **Monitoring Dashboard**: Real-time monitoring interface at `:8002` → Monitoring → Dashboard. Shows current cluster/host/forest/database/server metrics without historical retention. Point-in-time visibility only — no trend data or alerting.

- **Monitoring History**: Historical performance tracking backed by the Meters database. Must be enabled per group in Admin Interface › Groups › [group] › Monitoring History setting. Retains raw/hourly/daily metrics based on configured retention policies. Requires Meters database to be properly provisioned and replicated.

- **Ops Director**: Multi-cluster configuration history tool for tracking changes over time across MarkLogic estates. Deprecated starting MarkLogic 10.0-5, discontinued November 2021. Recommended replacement is external monitoring tools integrated via Management API.

- **Management REST API view=status**: Scriptable monitoring endpoints for external integration. Key endpoints: `GET /manage/v2/hosts/{id}?view=status`, `GET /manage/v2/databases/{id}?view=status`, `GET /manage/v2/servers/{id}?view=status`, `GET /manage/v2/forests/{id}?view=status`, and cluster-level status. Requires `manage-user` role or equivalent privileges.

- **No built-in operational alerting**: MarkLogic provides monitoring data collection and display but external tools are needed for operational alerting (CPU, disk, performance thresholds). Content alerting (document matching stored queries) exists but is separate from operational monitoring.

- **Meters database**: Special database storing monitoring history data. Created automatically when monitoring is enabled. Subject to same capacity planning and failover requirements as other databases. Growth depends on retention settings and cluster activity.

- **Server logs**: Logs live in the `Logs` directory under the MarkLogic data directory (typically `c:\Program Files\MarkLogic\Data\Logs` on Windows, `/var/opt/MarkLogic/Logs` on UNIX-based systems). `ErrorLog.txt` holds MarkLogic Server exceptions, startup activity and so on; `<port_no>_AccessLog.txt` holds access requests (for example HTTP requests) for the App Server on that port. Configurable: how long to keep a log before starting a new one, the level at which activity is logged, and how many old log files to keep before deleting. Old files get a number appended (`ErrorLog_5.txt` means 5 new log files have been created since this one was used). An App Server option writes uncaught application exceptions to `ErrorLog.txt` (so e.g. a syntax error is logged as well as sent to the client; useful when queries come from a browser or WebDAV client). `xdmp:log` writes a message at any level to `ErrorLog.txt` (useful in development and for logging activity in production). Some sites script log monitoring for specific messages to send alerts.

- **Log device disk space**: The filesystem holding the logs needs sufficient disk space. If there is no space left on the log device MarkLogic Server will abort; if there is no disk space for the log files it will fail to start.

- **Admin Interface status screens** (each on the Status tab of its part of the Admin Interface):

  | Screen | Location | Shows |
  | ------ | -------- | ----- |
  | System Status | Configure › Status | Summary of the whole cluster (hosts, App Servers, databases, forests); buttons to restart or shut down all hosts |
  | Group Status | Groups › group_name › Status | Same summary for the group |
  | Host Status | Hosts › host_name › Status | Current conditions on the host (App Servers, forests, active queries); buttons to enter a license key, restart, shut down |
  | App Server Status | Groups › group_name › App Servers › app_server_name › Status | Activity, including queries active on each host; can cancel queries |
  | Task Server Status | Groups › group_name › Task Server › Status | Requests being processed and tasks queued |
  | Database Status | Databases › db_name › Status | Merges and reindexing in progress with time estimates; documents, fragments, size; optionally forest status |
  | Forest Status | Forests › forest_name › Status | Merge activity, number of stands, size, space available; a restart button (takes the forest offline, then it tries to rejoin the host; with failover enabled it first tries its primary host) |

- **Server Monitoring APIs**: XQuery functions returning XML representations of current activity: `xdmp:forest-counts`, `xdmp:forest-status`, `xdmp:host-status`, `xdmp:request-cancel`, `xdmp:request-status`, `xdmp:server-status`. Use them to build your own reports or integrate with site-wide monitoring. `xdmp:forest-counts` can take some time on large systems because it queries the forest for some of the counts; its optional second argument limits the work. Syntax is in the "Server Monitoring functions" of the MarkLogic XQuery and XSLT Function Reference.

  Verified on the function pages (MarkLogic 12.0 reference). Host ID: `xdmp:host("name")`; server ID: `xdmp:server("name")` (forms used in the page examples).

  | Function | Parameters | Returns | Privilege |
  | -------- | ---------- | ------- | --------- |
  | `xdmp:request-status` | `$host-id` (must be the local host), `$server-id` (HTTP, XDBC, ODBC, WebDAV or Task server), `$request-id` (one or more) | `element(request-status)*`, one per requested ID that is running | none for the calling request's own ID; `http://marklogic.com/xdmp/privileges/status` for another request. Not cluster-aware: for a remote host use `xdmp:server-status` |
  | `xdmp:server-status` | `$host-id`, `$server-id` (one or more; HTTP, XDBC, ODBC, WebDAV or Task) | `element(server-status)*`, including per-request details | the page lists none |
  | `xdmp:host-status` | `$host-id` (one or more) | `element(host-status)*`; computed on the named host even when called from an App Server on another host | `http://marklogic.com/xdmp/privileges/status` |
  | `xdmp:forest-status` | `$forest-id` (one or more), optional `$options`: `memory-summary` or `memory-detail` | `element(forest-status)*` | `http://marklogic.com/xdmp/privileges/status` |
  | `xdmp:forest-counts` | `$forest-id` (one or more), optional `$show-elements` (names of count elements to compute; omitted or empty means all), optional `$options`: `preview-reindexer` or `preview-rebalancer` (only when `$show-elements` is empty) | `element(forest-counts)*`, one per forest; can take significantly longer than `xdmp:forest-status` | `http://marklogic.com/xdmp/privileges/counts` |
  | `xdmp:request-cancel` | `$hostID`, `$serverID`, `$requestID` (request IDs appear in the `request` elements of `xdmp:server-status` output) | `empty-sequence()`; once cancelled, the request no longer appears in `xdmp:server-status` output | `http://marklogic.com/xdmp/privileges/cancel-any-request` and `http://marklogic.com/xdmp/privileges/cancel-my-requests` (both listed on the page) |

## Standard procedures

1. **Enable Monitoring History**: Admin Interface → Groups → [group-name] → Configure tab → Monitoring History section → Enable monitoring history → Set retention periods → Apply
2. **Access Monitoring Dashboard**: Open browser → `https://[host]:8002/` → Monitoring → Dashboard → View real-time metrics by resource type
3. **View Monitoring History**: Browser → `https://[host]:8002/` → Monitoring → History → Select time range and resource → Analyze historical trends
4. **Check host status via API**: `curl -X GET "http://[host]:8002/manage/v2/hosts/[hostname]?view=status" --anyauth -u [user:pass]` → Parse JSON response for operational metrics
5. **Monitor database status**: `curl -X GET "http://[host]:8002/manage/v2/databases/[db-name]?view=status" --anyauth -u [user:pass]` → Check forest states, indexing progress
6. **Monitor app server status**: `curl -X GET "http://[host]:8002/manage/v2/servers/[server-name]?view=status" --anyauth -u [user:pass]` → Check thread utilization, queue depth
7. **Set up external monitoring**: Create monitoring account with `manage-user` role → Script periodic API calls → Parse status responses → Configure alerting thresholds
8. **Check ErrorLog.txt for the incident window**: open `ErrorLog.txt` (and numbered older files such as `ErrorLog_5.txt` if the window has rotated) in the Logs directory → read entries for the incident time range
9. **Check disk space on the Logs filesystem** when MarkLogic aborts or will not start: confirm free space on the device holding the Logs directory → free space, then restart
10. **Open the relevant status screen**: System Status (cluster), Group Status, Host Status, App Server Status, Task Server Status, Database Status or Forest Status for the resource in question
11. **Script reports with the monitoring functions**: build reports or feed site-wide monitoring from `xdmp:server-status`, `xdmp:host-status`, `xdmp:forest-status`, `xdmp:request-status` etc.; take syntax from "Server Monitoring functions" in the MarkLogic XQuery and XSLT Function Reference

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --------- | ------------------------- | ---------------- | ------------------- | --------- |
| Monitoring History never enabled | No historical data available when investigating an incident after the fact; support has to reconstruct everything from raw logs | Admin Interface › Groups › [group] › Configure › Performance Metering Enabled shows "false" | Enable Monitoring History per group before an incident, not after | <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/marklogic-server-monitoring-history/enable-monitoring-history-on-a-group.html> |
| Meters database itself has no replica / is under-provisioned | The one database meant to help diagnose problems becomes unavailable during the same host failure it should explain | Check Meters forest count/replicas the same way as any content database (see databases-forests.md / ha-backup-failover.md) | Treat Meters like any other database needing capacity planning and failover | <https://help.marklogic.com/Knowledgebase/Article/View/399> |
| Relying only on the point-in-time Dashboard | No trend data before a case is opened; "it was fine when I looked yesterday" | Check if Monitoring History is enabled and has data for incident timeframe | Pair the Dashboard (current state) with Monitoring History or external tooling (trends) | <https://docs.marklogic.com/9.0/guide/monitoring/dashboard> |
| No alerting wired to Management API for ErrorLog levels or operational thresholds | Incidents discovered only when the customer calls, hours after they began | Ask what triggers a page/alert today; check whether anything polls `?view=status` or ErrorLog levels | Poll `GET /manage/v2/...?view=status` and ErrorLog Critical/Error counts on a schedule; alert on operational thresholds | <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/introduction/select-a-monitoring-tool.html> |
| Confusing host-level metrics with app-server-level saturation | "The host looks fine" while one app server's request queue/threads are exhausted | Compare host CPU/RAM (Host Status) against the specific app server's `threads`/`max-threads`/queue in its status view | Check `GET /manage/v2/servers/{name}?view=status` per app server, not only host metrics | <https://docs.marklogic.com/REST/GET/manage/v2/hosts/%5Bid-or-name%5D@view=status> |
| Monitoring/service account lacks `manage-user` role or equivalent privilege | Status queries return partial/empty data with no obvious error | Check the account's roles against the Management API's required privileges | Grant `manage-user` role to the monitoring account | <https://docs.marklogic.com/9.0/guide/monitoring/monitoringAPI> |
| No baseline captured before go-live or before a change | Can't tell "abnormal" from "normal for this app" when a ticket comes in | Ask whether a baseline of normal cache hit rates / request rates / forest sizes exists | Capture and keep a baseline snapshot after go-live and after major changes | <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/introduction/guidelines-for-configuring-your-monitoring-tools/establish-a-performance-baseline.html> |
| Ops Director not configured for multi-cluster estate management | Configuration drift between clusters goes unnoticed until it causes an incident | Ask how many clusters they run and how config changes are tracked across them; note: Ops Director deprecated Nov 2021 | Use external configuration management or monitoring tools to track consistency across clusters | [unverified — confirm] |
| Meters database retention settings too aggressive | Historical data purged before investigations complete; inability to establish trends | Check Meters database retention settings vs typical incident investigation timeframes | Size retention periods for your MTTR + buffer; balance storage cost vs investigation needs | <https://help.marklogic.com/knowledgebase/article/View/259/0> |
| Log device full | MarkLogic Server aborts, or fails to start because there is no disk space for the log files | Check free space on the filesystem holding the Logs directory | Keep sufficient free disk space on the log device; monitor it and trim old logs | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html#id_80312> (page "Monitoring MarkLogic Server Performance", MarkLogic 12.0) |
| Calling `xdmp:forest-counts` repeatedly on a large system without limiting the work | Monitoring script or report is slow; load on the forests | Review what the script calls and how often; the function queries the forest for some counts | Call it sparingly and use its optional second argument to limit the work (see Function Reference) | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html#id_80312> (page "Monitoring MarkLogic Server Performance", MarkLogic 12.0) |
| Not enabling the App Server option for writing uncaught exceptions to ErrorLog.txt | Application errors (e.g. syntax errors) reach only the client; nothing in `ErrorLog.txt` to correlate | Check the App Server configuration for the option and look for the error in `ErrorLog.txt` | Enable the App Server option for writing uncaught exceptions to ErrorLog.txt, especially when queries are generated from a browser or WebDAV client | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html#id_80312> (page "Monitoring MarkLogic Server Performance", MarkLogic 12.0) |
| Log retention too short | Old `ErrorLog` files already deleted when an investigation starts | Confirm the configured number of old log files and how long a log is kept before a new one starts | Raise the number of old log files kept / log lifetime to cover investigation time | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html#id_80312> (page "Monitoring MarkLogic Server Performance", MarkLogic 12.0) |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/introduction.html>
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/introduction/select-a-monitoring-tool.html>
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/use-the-marklogic-server-monitoring-dashboard/display-the-monitoring-dashboard.html>
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/marklogic-server-monitoring-history/view-monitoring-history.html>
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/marklogic-server-monitoring-history/enable-monitoring-history-on-a-group.html>
- <https://docs.progress.com/bundle/marklogic-server-monitor-12/page/topics/introduction/guidelines-for-configuring-your-monitoring-tools/establish-a-performance-baseline.html>
- <https://docs.marklogic.com/9.0/guide/monitoring/dashboard>
- <https://docs.marklogic.com/9.0/guide/monitoring/monitoringAPI>
- <https://docs.marklogic.com/REST/GET/manage/v2/hosts/%5Bid-or-name%5D@view=status>
- <https://docs.marklogic.com/REST/GET/manage/v2/databases/%5Bid-or-name%5D@view=status>
- <https://help.marklogic.com/Knowledgebase/Article/View/399>
- <https://help.marklogic.com/knowledgebase/article/View/259/0>
- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html#id_80312> (page "Monitoring MarkLogic Server Performance", MarkLogic 12.0; read on 2026-10-21, it covers the logs, the disk-space abort, the seven status screens, the six functions and the forest-counts note)
- <https://docs.marklogic.com/xdmp:request-status>
- <https://docs.marklogic.com/xdmp:server-status>
- <https://docs.marklogic.com/xdmp:host-status>
- <https://docs.marklogic.com/xdmp:forest-status>
- <https://docs.marklogic.com/xdmp:request-cancel>
- <https://docs.marklogic.com/xdmp:forest-counts>
