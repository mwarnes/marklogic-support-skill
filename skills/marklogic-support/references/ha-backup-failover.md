# High Availability, Backup, and Failover — keeping data available and recoverable

## Concepts

- **Failover types**: Two approaches to maintain data availability during host failure. **Local-disk failover** creates replica forests on different hosts, synchronously updated via journal frames. **Shared-disk failover** uses clustered filesystem (VxFS, GFS, GFS2) or NFS where failover hosts can mount failed forests at the same path.

- **Forest states**: Primary forest is **open** and attached to database. Replica forests: **sync replicating** (caught up, ready for failover), **async replicating** (catching up after being added or offline), **wait replicating** (startup/post-failover transition state). Only sync replicating replicas can handle failover.

- **Quorum requirement**: Failover only triggers when >50% of cluster hosts agree a host is down (based on 30-second heartbeat timeout). Minimum 3 hosts needed for failover; 2-host clusters can't achieve quorum. Prevents split-brain scenarios where network partition creates two half-clusters.

- **Failback**: Failed hosts don't automatically reclaim forests when restored. Administrator must manually restart forests to avoid "ping-pong" if primary host has recurring issues. Replica data resynchronizes before forest becomes primary again.

- **Backup types**: **Full backup** captures complete database state. **Incremental backup** captures only changes since last backup. **Journal archiving** continuously streams journal frames to backup location for point-in-time recovery. Backups can include Security, Schemas, and Triggers databases.

- **Point-in-time recovery**: Requires journal archiving enabled with lag limit (seconds between forest journal and backup journal). Reconstructs database to any timestamp since last full backup by replaying archived journal frames during restore.

## Standard procedures

1. **Enable failover (prerequisite)**: set `failover enable` to true on the group (Groups › [group] › Configure; `admin:group-set-failover-enable`) and on each forest (Forests › [forest] › Configure; `admin:forest-set-failover-enable`) — both must be true. Enabling alone protects nothing: steps 2–3 configure each forest's replica forests (local-disk) or failover hosts (shared-disk).

2. **Configure local-disk failover**: For each forest, add replica forests on different hosts. Create forest → specify different host → configure as replica of primary. Verify replica state shows "sync replicating" (not "wait replicating" or "async replicating").

3. **Configure shared-disk failover**: Create forest with data directory on shared storage (SAN/NFS) accessible at same path on all failover hosts. Forest settings → Failover Enable = true → specify failover hosts in priority order.

4. **Test failover behavior**: Gracefully shutdown primary host. Verify replica forest promotes to primary and database remains accessible. Check forest status in Admin Interface shows failover host mounting forest.

5. **Schedule backups with journal archiving**: Create scheduled task → Database backup → Enable "Archive Journals" → Set lag limit (e.g., 60 seconds) → Choose shared backup directory accessible to all hosts → Include Security/Schemas/Triggers databases.

6. **Set up incremental backups**: After initial full backup, configure incremental backup schedule → Enable "Incremental Backup" option → Ensure journal archiving remains enabled for point-in-time recovery capability.

7. **Test restore procedure**: Practice restore from different backup timestamps → Verify Security database restore maintains user access → Test restore to different cluster with forest name mapping if needed.

8. **Fail back after host recovery**: When failed host returns, resynchronize data → Admin Interface → Forest → Restart to move forest back to primary host. Monitor replica rebuilding process.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --------- | ------------------------- | ---------------- | ------------------- | --------- |
| Failover enabled on DB but no replica forests / failover hosts | Database becomes unavailable for query operations when host fails | Check forest config for replica forests or failover hosts list | Add replica forest per primary forest on different host, or configure failover hosts for shared-disk | <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/failover.html> |
| Replica forest on same host as master | Failover useless, both forests lost on host failure | Compare forest host vs replica forest host | Move replica to different physical host | <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/failover.html> |
| Replica host lacks RAM/disk for failed-over forests | OOM, disk full, poor performance after failover | Check capacity of failover hosts assuming N-1 failure | Size failover hosts to handle their own forests plus failed-over load | Inside MarkLogic p.104-105 |
| 2-host cluster expecting failover | Failover never happens, forests stay unavailable | Count cluster hosts, check quorum math | Require ≥3 hosts for quorum >50% | Inside MarkLogic p.105 |
| Never failing back after host recovery | Load imbalance, replicas' replicas missing | Forest status shows "open replica" on wrong host indefinitely | Manual restart/failback procedure after host stabilizes | <https://help.marklogic.com/Knowledgebase/Article/View/564/0/should-i-flip-failed-over-forests-back-to-their-respective-masters--what-are-the-risks-if-i-leave-them> |
| Replica forest name doesn't match master name | Forests stuck in "Wait Replication" state | Forest status shows wait replicating, check forest names | Ensure replica forest names match primary forest names exactly | <https://help.marklogic.com/Knowledgebase/Article/View/143/0/wait-replication-state-due-to-forest-name-mismatch> |
| Backups only on local disk of failed host | Backup lost with host, cannot restore | Check backup directory location | Use shared storage (NFS/SAN) or remote location (S3) for backups | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/backing-up-and-restoring-a-database.html> |
| Incremental backup without journal archiving where PITR required | Cannot restore to specific point in time, only to backup snapshots | Check backup config for journal archiving setting | Enable journal archiving with appropriate lag limit | <https://help.marklogic.com/knowledgebase/article/View/215/0/point-in-time-recovery-using-incremental-backup-with-journal-archiving> |
| Security DB not included in backup set | Restored DB inaccessible due to missing users/roles | Check backup includes auxiliary databases | Include Security, Schemas, Triggers in backup configuration | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/backing-up-and-restoring-a-database.html> |
| Restore from different cluster without matching forest names | XDMP-FORESTNOT or forest mapping errors during restore | Compare forest names between backup and target cluster | Create matching forest names on target or use restore mapping options | <https://help.marklogic.com/Knowledgebase/Article/View/535/0/restoring-from-incremental-backup-taken-on-a-different-cluster> |
| Backups scheduled during merges/reindex/peak load | Backup timeouts, XDMP-BACKUP* failures, performance impact | Check backup schedule vs merge/reindex activity and usage patterns | Schedule backups during maintenance windows, stagger across hosts | <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/scheduling-tasks.html> |
| Journal archiving lag limit too small for workload | Transaction halts when backup journal can't keep up | Monitor journal archiving lag vs limit, check error logs for lag exceeded | Increase lag limit or improve backup storage performance | <https://docs.marklogic.com/admin-help/database> |
| Shared-disk failover without supported clustered filesystem | Forest cannot be configured for failover, failover setup fails | Check if forest data directory is on supported CFS (VxFS, GFS2) or NFS | Move forest to supported clustered filesystem or NFS accessible at same path on all hosts | <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/failover.html> |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/failover.html>
- <https://docs.progress.com/bundle/marklogic-server-configure-scal-avail-perf-12/page/topics/config_failover.html>
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/backing-up-and-restoring-a-database.html>
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/scheduling-tasks.html>
- <https://docs.marklogic.com/admin-help/database>
- <https://help.marklogic.com/Knowledgebase/Article/View/143/0/wait-replication-state-due-to-forest-name-mismatch>
- <https://help.marklogic.com/Knowledgebase/Article/View/564/0/should-i-flip-failed-over-forests-back-to-their-respective-masters--what-are-the-risks-if-i-leave-them>
- <https://help.marklogic.com/knowledgebase/article/View/215/0/point-in-time-recovery-using-incremental-backup-with-journal-archiving>
- <https://help.marklogic.com/Knowledgebase/Article/View/535/0/restoring-from-incremental-backup-taken-on-a-different-cluster>
- Inside MarkLogic Server p.104-110 — Failover and Replication section
