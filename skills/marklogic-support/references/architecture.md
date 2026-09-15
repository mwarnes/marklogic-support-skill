# MarkLogic architecture — how the pieces fit

## Concepts

- **Cluster → Groups → Hosts**: A group holds config shared by its hosts (app servers, cache sizes, schedulers, log levels). A host belongs to exactly one group. Groups communicate using XDQP protocol on port 7999.

- **E-nodes and D-nodes**: Hosts are E-nodes (evaluate: run app servers, XQuery/JS, coordinate queries) and/or D-nodes (data: host forests). Small clusters combine roles; large ones separate them. Load balancer spreads queries across E-nodes.

- **Database structure**: Database = ordered set of forests + index configuration. Forest = physical store on one host, made of stands (read-only, immutable after write) + journals + in-memory stand.

- **Write flow**: Writes → journal + in-memory stand → flushed to on-disk stand; merges combine stands, drop deleted fragments, are I/O-heavy and need free disk (~1.5–2× largest forest as headroom).

- **Universal Index**: Indexes words, phrases, structural elements, and metadata. Term lists over element/attribute/word content enable fast search without schema knowledge. Index settings are per-database → changing them triggers reindex across all forests.

- **Range indexes**: In-memory, per-forest, built at reindex. Used for typed queries (dates, numbers) alongside universal index.

- **MVCC model**: Multi-Version Concurrency Control. Documents marked as deleted, not modified in place. Each fragment gets creation-time and deletion-time timestamps. Enables lock-free queries.

- **Caches**: Per-group, sized in MB, allocated per host at start. List cache (term lists), compressed tree cache (document fragments on disk), expanded tree cache (fragments in memory), triple cache/value cache. Sum must fit RAM alongside range indexes and OS.

- **Request flow**: Client → app server port on E-node → query evaluated → D-nodes answer per forest from index → results merged on E-node → returned to client.

- **App servers**: Port + root + content DB + modules DB (or filesystem) + auth + default user + timeouts + thread limits. Belongs to a group so runs on every host in it. Types: HTTP, XDBC, WebDAV, ODBC.

- **Security database**: Users, roles, privileges (execute/URI), amps, certificate templates. One per cluster (usually `Security` database).

- **Stands and merges**: On-disk stands accumulate until background merges combine them. Merge max size defaults to 32GB. Merges are CPU/disk-intensive, administratively controlled.

- **Failover**: Local-disk (replica forests on other hosts) vs shared-disk (forest moved to a failover host). Requires quorum (>50% of hosts) to prevent split-brain.

- **Rebalancer**: Assignment policy (bucket, legacy, statistical, range, query) decides which forest gets each document during ingestion or rebalancing operations.

## Standard procedures

1. Initial install → join cluster by providing existing cluster member hostname and group name
2. Create group with appropriate configuration (cache sizes, schedulers, app server defaults)  
3. Add host to group through Admin Interface, configure group membership
4. Create forests on hosts, typically multiple per host for parallelism
5. Create database and attach forests in desired order for proper distribution
6. Create app server with content DB, modules DB, authentication, and port binding
7. Configure security: users, roles, privileges, amps in Security database
8. Set up backups: scheduled database backups including Security database
9. Enable failover: configure replica forests or shared-disk failover with quorum
10. Index changes: modify database index settings → wait for reindex completion across all forests
11. Add capacity: add host & forests → trigger rebalancer to redistribute content

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --------- | ------------------------- | ---------------- | ------------------- | --------- |
| Index change on large DB during peak hours | Queries slow/timeout during reindex | Check reindexing status, forest timestamps | Schedule index changes during maintenance windows | Inside MarkLogic p.22 |
| Cache sizes sum exceeds available RAM | Out of memory errors, swap thrashing | Check cache settings vs RAM, OS memory usage | Size caches to leave 30%+ RAM for OS and range indexes | Inside MarkLogic p.48 |
| Single forest for huge database | Ingestion bottleneck, merge delays | Forest count vs data volume, merge activity | Use multiple forests per database for parallel I/O | Inside MarkLogic p.36 |
| Modules stored on filesystem in multi-host group | Module changes not reflected on all hosts | Module deployment inconsistency | Store modules in database for cluster consistency | Inside MarkLogic p.102 |
| Even host count without proper quorum consideration | Failover fails, split-brain scenario | Quorum calculation, failover testing | Maintain >50% hosts for quorum, odd numbers preferred | Inside MarkLogic p.104 |
| Insufficient disk space for merges | Merge failures, disk full errors | Free disk space vs largest forest size | Maintain 1.5-2× largest forest size as free space | Inside MarkLogic p.36 |
| D-node cache settings on E-node group | Poor query performance, cache misses | Cache hit rates, E-node vs D-node config | Optimize cache sizes per node role (E vs D) | Inside MarkLogic p.48 |
| No journal archiving setup | Point-in-time recovery unavailable | Journal archive configuration | Enable journal archiving for disaster recovery | Inside MarkLogic p.104 |

## Sources

- Inside MarkLogic Server (PDF, 127 pp.) — ch. 1-2 overview (p.7-11), indexing (p.12-22), clustering & caching (p.47-52), forests/stands/merges (p.35-38), MVCC (p.38-39), failover (p.104-110)
- <https://docs.progress.com/bundle/marklogic-server-administrate-12/page/topics/introduction/architecture-overview.html>
