# Database and forest configuration — storage and index management

## Concepts

- **Database → forests relationship**: Database = ordered set of forests + index configuration. Forest = physical store on one host, made of stands (read-only, immutable after write) + journals + in-memory stand. Database index settings apply to all attached forests.

- **Stands and merges**: Forests contain stands. In-memory stand holds new/changed documents until checkpointed to on-disk stand (sequential names: 00000000, 00000001...). Merges combine stands to optimize performance, remove deleted fragments, create larger stands up to merge max size (default 32GB).

- **Forest sizing rule of thumb**: Keep forests below ~512GB for manageable merge times and restart performance. Split large forests across multiple hosts rather than growing single forests too large.

- **Directory storage**: Data directory (main storage), fast data directory (SSD for journals/stands, spills to data directory when full), large data directory (for large objects).

- **Reindexing**: Triggered by index configuration changes on database. Runs in batches (~200 fragments), throttle controls resource priority (1-5 scale, 5=aggressive). Can take hours/days on large databases.

- **Rebalancing**: Assignment policy (bucket/legacy/statistical/range/query) decides which forest gets new documents. Rebalancer redistributes content after adding/removing forests.

- **Fragment settings**: Fragment root/parent settings control document fragmentation. Directory creation (automatic/manual/manual-enforced) affects WebDAV behavior and fragment patterns.

- **Memory settings**: In-memory limits control stand sizes before checkpoint to disk. Journal size controls transaction durability. Settings affect recovery time vs performance.

- **Index bloat factors**: Word positions (for phrase/near queries), wildcard searches, element range indexes. Each adds storage overhead and reindex time.

## Standard procedures

1. **Create forest**: Choose host → set data directory, optional fast/large data directories → attach to database in appropriate order for load distribution
2. **Add index**: Database → Index Settings → enable specific indexes → reindexer automatically starts if enabled → monitor completion before relying on index
3. **Configure merge schedule**: Set merge blackout periods to avoid I/O-intensive merges during peak hours
4. **Enable rebalancer**: After adding forests, enable rebalancer to redistribute content across new topology
5. **Retire forest safely**: Disable rebalancer → detach forest from database → verify no active queries → optionally keep data for recovery → delete forest
6. **Change assignment policy**: Plan for rebalancing impact → change policy → enable rebalancer → monitor redistribution progress
7. **Database backup**: See `ha-backup-failover.md` for backup procedures including journal archiving for point-in-time recovery

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --------- | ------------------------- | ---------------- | ------------------- | --------- |
| Forest grown past ~512 GB (rule of thumb) | Slow merges, long restarts, huge disk headroom needed for merges | Forest status shows size; merge activity logs | Split across more forests/hosts; use rebalancer to redistribute | [unverified — confirm] |
| Insufficient free disk for merges | `XDMP-FORESTNOSPACE` errors, merges stall, forest goes read-only | Check free disk vs largest forest size | Maintain ≥1.5-2× largest forest size as free space; reduce merge max size if needed | <https://help.marklogic.com/knowledgebase/article/View/284/0/understanding-marklogic-minimum-disk-space-requirements> |
| Adding many indexes (positions, wildcards, all-elements range) without capacity planning | Index bloat, slow ingest, reindexing takes days | Check database index settings; compare on-disk index proportion | Add only needed indexes; enable word positions only where phrase/near queries required | <https://help.marklogic.com/knowledgebase/article/View/113/0/indexing-best-practices> |
| Reindex kicked off during peak hours with reindexer throttle 5 | Query latency spike, I/O saturation | Database status shows "reindexing"; check throttle setting; `admin:database-get-reindexer-throttle($config, $db-id)` | Lower throttle (1-2) or schedule index changes for off-peak windows; `admin:database-set-reindexer-throttle($config, $db-id, 1)` (Admin API, `import module namespace admin = "http://marklogic.com/xdmp/admin" at "/MarkLogic/admin.xqy"`; save with `admin:save-configuration`). REST: `PUT /manage/v2/databases/{id-or-name}/properties` with `{"reindexer-throttle": 1}` | <https://help.marklogic.com/knowledgebase/article/View/113/0/indexing-best-practices> |
| Reindexer disabled after index change and forgotten | New index settings not applied to existing documents; queries relying on the new index miss or return inconsistent results | Check `reindexer enable = false` with pending index changes | Re-enable reindexer; verify reindex completion before production | <https://docs.marklogic.com/admin-help/database> |
| Rebalancer disabled after adding forests | New forests empty while others overloaded, uneven query performance | Compare forest document counts; check rebalancer enable setting | Enable rebalancer; verify assignment policy matches use case | <https://docs.marklogic.com/admin-help/database> |
| Directory creation set to `automatic` for high-volume ingest | Many directory fragments created, lock contention, slower ingest | Check database directory creation setting | Set to `manual` unless WebDAV access required | [unverified — confirm] |
| Fragment root/parent defined without justification | Excessive fragmentation, complex query semantics | Check database fragment settings against query patterns | Remove fragment settings unless specific query optimization needed | [unverified — confirm] |
| Single forest for large database (no parallelism) | Ingest and query bottleneck on single host | Forest count vs data size; single host handling all load | Create multiple forests per host (≤ vCPU/2 guidance); distribute across hosts | Inside MarkLogic p.36 |
| Deleting forest still attached to database | Data loss, `XDMP-FORESTNOT` errors on queries | Check database forest attachments before deletion | Detach forest → verify queries work → optionally delete forest data | [unverified — confirm] |
| Merge blackout set as permanent/too wide | Stand count balloons, query performance degrades | Check merge policy blackout windows; forest stand counts | Limit blackout to genuine maintenance windows only | [unverified — confirm] |
| Locking set to `off` on frequently updated database | Inconsistent reads, lost updates, duplicate URIs | Check database locking setting | Keep locking `strict` unless bulk-loading new documents only | <https://docs.marklogic.com/admin-help/database> |
| Fast data directory undersized for forest load | Journals/stands spill to slower data directory prematurely | Check fast data max size vs actual usage | Size fast data directory for expected active working set | <https://docs.marklogic.com/admin-help/forest> |
| Journal size too small for transaction volume | Frequent journal rollovers, reduced durability window | Monitor journal rollover frequency in logs | Increase journal size based on transaction patterns and durability needs | <https://docs.marklogic.com/admin-help/database> |
| Too many stands accumulating (merge policy issues) | Query performance drops, "Emergency: Stand has n fragments" | Check stand counts per forest in Admin Console | Review merge policy settings; ensure merges can complete | <https://help.marklogic.com/Knowledgebase/Article/View/291/0/emergency-stand-has-n-fragments-message> |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/databases.html>
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/forests.html>
- <https://docs.marklogic.com/admin-help/database>
- <https://docs.marklogic.com/admin-help/forest>
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/scalability.html>
- <https://help.marklogic.com/knowledgebase/article/View/284/0/understanding-marklogic-minimum-disk-space-requirements>
- <https://help.marklogic.com/knowledgebase/article/View/113/0/indexing-best-practices>
- <https://help.marklogic.com/Knowledgebase/Article/View/10/0/how-does-the-number-of-stands-impact-performance-and-how-does-merging-help>
- <https://help.marklogic.com/Knowledgebase/Article/View/291/0/emergency-stand-has-n-fragments-message>
- <https://help.marklogic.com/knowledgebase/article/View/18/15/how-reindexing-works-and-its-impact-on-performance>
- Inside MarkLogic p.35-38
