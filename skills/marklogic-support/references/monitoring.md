# Monitoring — real-time dashboard, historical data, and external integration

## Concepts

- **Monitoring Dashboard**: Real-time monitoring interface at `:8002` → Monitoring → Dashboard. Shows current cluster/host/forest/database/server metrics without historical retention. Point-in-time visibility only — no trend data or alerting.

- **Monitoring History**: Historical performance tracking backed by the Meters database. Must be enabled per group in Admin Interface › Groups › [group] › Monitoring History setting. Retains raw/hourly/daily metrics based on configured retention policies. Requires Meters database to be properly provisioned and replicated.

- **Ops Director**: Multi-cluster configuration history tool for tracking changes over time across MarkLogic estates. Deprecated starting MarkLogic 10.0-5, discontinued November 2021. Recommended replacement is external monitoring tools integrated via Management API.

- **Management REST API view=status**: Scriptable monitoring endpoints for external integration. Key endpoints: `GET /manage/v2/hosts/{id}?view=status`, `GET /manage/v2/databases/{id}?view=status`, `GET /manage/v2/servers/{id}?view=status`, `GET /manage/v2/forests/{id}?view=status`, and cluster-level status. Requires `manage-user` role or equivalent privileges.

- **No built-in operational alerting**: MarkLogic provides monitoring data collection and display but external tools are needed for operational alerting (CPU, disk, performance thresholds). Content alerting (document matching stored queries) exists but is separate from operational monitoring.

- **Meters database**: Special database storing monitoring history data. Created automatically when monitoring is enabled. Subject to same capacity planning and failover requirements as other databases. Growth depends on retention settings and cluster activity.

## Standard procedures

1. **Enable Monitoring History**: Admin Interface → Groups → [group-name] → Configure tab → Monitoring History section → Enable monitoring history → Set retention periods → Apply
2. **Access Monitoring Dashboard**: Open browser → `https://[host]:8002/` → Monitoring → Dashboard → View real-time metrics by resource type
3. **View Monitoring History**: Browser → `https://[host]:8002/` → Monitoring → History → Select time range and resource → Analyze historical trends
4. **Check host status via API**: `curl -X GET "http://[host]:8002/manage/v2/hosts/[hostname]?view=status" --anyauth -u [user:pass]` → Parse JSON response for operational metrics
5. **Monitor database status**: `curl -X GET "http://[host]:8002/manage/v2/databases/[db-name]?view=status" --anyauth -u [user:pass]` → Check forest states, indexing progress
6. **Monitor app server status**: `curl -X GET "http://[host]:8002/manage/v2/servers/[server-name]?view=status" --anyauth -u [user:pass]` → Check thread utilization, queue depth
7. **Set up external monitoring**: Create monitoring account with `manage-user` role → Script periodic API calls → Parse status responses → Configure alerting thresholds

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
