# MarkLogic internals: indexes, update model, locking, clustering, backup, replication, rebalancing

Use when a ticket needs the mechanism behind a symptom: why a query is filtered, what an update locks, why a read is stale, what a backup or failover really does, why a forest is unbalanced. For what each activity costs in disk, CPU, memory and network see `resource-consumption.md`.

**Version warning.** Source: "Inside MarkLogic Server" (J. Hunter and M. Wooldridge, 3rd edition, covers MarkLogic 8, April 2016). The mechanisms still hold; defaults, limits and option names may have changed in 11/12. Numbers and defaults below are paraphrased from the book and must be checked against current documentation before being quoted to a customer (`[unverified — confirm for 11/12]`). Page numbers are the book's printed pages. The text is paraphrased, never quoted.

## Concepts

**Indexing and search**
- **Term lists.** The Universal Index holds one term list per word, phrase, element, value, collection, directory and security role. A query intersects, unions or subtracts term lists to get candidate fragments (index resolution); each step uses cached term lists or reads them from disk (p.12-15, 22-23).
- **Phrases.** Three ways: fast phrase searches (word-pair terms), word positions (position matching, also needed for NEAR and "mild not"), or neither (filter candidates). Position work costs time and memory in proportion to the terms examined, so positions are combined with word pairs. More index options mean tighter candidates and fewer discarded documents (p.13-15).
- **Always-on indexes.** The parent-child element index and the element-value index exist whatever the settings; term-list keys are hashes. Values are stored as text, so typed or range comparisons need a range index (p.16-17).
- **Filtering.** After index resolution a filtered search opens each candidate to drop false positives. Results are the same filtered or unfiltered; only speed and tightness differ. `cts:search` is filtered unless `"unfiltered"` is passed; `search:search` is unfiltered by default (p.14, 16, 22, 26).
- **Estimate versus count.** `xdmp:estimate` counts fragments from indexes only (fast, can be higher or lower than the truth); `fn:count` filters and counts exactly (slow). Aim for index settings where the two agree, so nothing is read from disk just to be discarded (p.25-26).
- **Plans.** `xdmp:plan` shows the index constraints a path or `cts:search` uses, including how a wildcard is resolved (p.19, 72).
- **Fragments.** The unit of indexing, retrieval and update; default is the document. Fragment root/parent applies to XML only, not JSON. Prefer one item per document: locks are per document and updates replace whole fragments (p.24-25, 41).
- **Index size.** With default indexes the on-disk size can be below the source XML; with many indexes two to three times; wildcard support can add more than three times (p.19). Fields scope costly indexes (wildcards, weights) to the parts that need them (p.19, 75-77).
- **Reindexing.** Runs in the background without stopping queries or updates. A newly added index cannot serve requests until reindexing completes; a removed index stops being used at once. Throttle 5 (eager) to 1, or switch it off; with the reindexer off and an index disabled, the index data is still maintained, which gives a cheap with/without test (p.19).
- **Range indexes.** Two memory-mapped arrays (document to value, value to document). They serve range queries, typed equality, value extraction and facets, optimised `order by`, joins and bitemporal queries. Without one, a range predicate cannot use any index and every candidate is examined (p.26-29). JSON numbers and Booleans compare for equality without a range index but not for inequality (p.29). About 10 million lookups per second per core, integers fastest, simple codepoint collation faster than others (p.31). Path range indexes are more specific but cost more to compute and filter; use plain element indexes if they suffice (p.32).
- **Lexicons.** URI and collection lexicons are range indexes in disguise; the word lexicon is a flat word list. A word lexicon on the codepoint collation helps wildcards (p.33, 72).
- **Wildcards.** Trailing-wildcard index, three-character index and word-lexicon expansion (full, or prefix/suffix) are chosen by heuristics from index settings and data statistics; hints are allowed (p.71-72).
- **Text options.** Case-sensitive terms resolve with filtering unless fast case-sensitive searches is on; same for diacritics. Stemming defaults differ by version: stemmed on and word searches off up to 8, reversed in 9. Advanced stemming and decompounding enlarge the index (p.67-69).
- **Positions limit.** A term whose position list passes the positions-list-max-size limit loses its positions for query resolution; a non-empty `StopKeySet` file in a stand shows it happened (p.75).
- **Relevance.** Default is log-tf-idf. `score-zero` skips scoring. Relevance tracing is costly and not for production (p.73-75).
- **Registered queries.** Cached as synthetic term lists in the List Cache, per stand; lost on restart and aged out of the cache, so register just before use (p.77-80).
- **Properties.** A query constraining both a document and its properties does a hash join on the URI (p.24).
- **Security.** Every query is intersected with the term lists of the user's roles; compartment security intersects them instead of uniting them (p.23).

**Update model**
- **Stands and merges.** New documents go to the in-memory stand and the journal, are flushed to numbered on-disk stands, and merges combine stands in the background up to the merge max size (32 GB default from MarkLogic 7). Free space needed is about 50% of the forest size (p.35-37, footnote 7). Detail and limits are in `resource-consumption.md`.
- **MVCC.** Each fragment has a creation and a deletion timestamp (the `Timestamps` file is the only writable file in a stand). Queries run at one timestamp, lock-free. An update marks the old fragment deleted and writes a new one; merges drop deleted fragments (p.37-38).
- **Point-in-time.** Queries at an older timestamp work only while merges have not reclaimed the deleted fragments, controlled by the database merge timestamp (and retention settings) (p.38-39).
- **Locking.** Read and write locks per document, first come first served; a waiting write lock blocks new read locks on the same document. Deadlocks are found by a background thread; the update with most progress wins and the other restarts (p.39). `xdmp:lock-for-update` takes a write lock without writing, to avoid repeating work after a restart or to serialise statements (p.39).
- **Query or update.** XQuery decides by static analysis (an `xdmp:update` prolog forces update); JavaScript needs `declareUpdate()`. Lock-free queries outperform updates that must lock, so isolate updates in their own transaction with `xdmp:eval`, `xdmp:invoke` or `xdmp:spawn` when the query does not depend on them (p.40-41).
- **Nascent fragments.** Fragments written but not yet committed; a big transactional insert accumulates many, visible on the Admin status pages (p.42).
- **Commit.** Parse and index, write to the in-memory stand as nascent, obtain a timestamp, journal the intent, then set the creation timestamp. Across forests the D-nodes run a two-phase commit with a coordinator (p.42, 53-55).
- **Multi-statement and XA transactions.** Statements see their own pending changes through per-transaction added and deleted lists. A deadlock cannot be retried automatically, so the client gets a retryable exception; a restart of any participating server rolls the transaction back. XA goes through JTA (p.43-45).
- **Isolation.** Read-only transactions are serializable thanks to MVCC; update transactions are repeatable read, with one phantom-read loophole (a new matching insert) closed by locking a sentinel URI (p.56-57).
- **Storage types.** Fast data directory: a small SSD share (the book says 5% to 10% of capacity, SLC flash, PCI or dedicated controller) holds journals and the smallest stands (p.45). Binaries above the large size threshold (default 1 MB, 32 KB to 512 MB) live in a `Large` directory or a large data directory, outside merges; external binaries are managed by the application and fetched by E-nodes (p.46, 49).

**Cluster**
- **Roles.** E-nodes evaluate and coalesce; D-nodes resolve indexes and return iterators of fragment IDs and scores; the E-node fetches only the fragments it needs (expanded tree cache, then D-node compressed tree cache, then disk) (p.47-48, 52-53).
- **Groups and ports.** Hosts in a group share configuration; XDQP between hosts uses port 7999 (p.48).
- **Caches.** Default sizes assume a combined E/D host. D-node groups need a small expanded tree cache but not zero (the book suggests about 128 MB: reindexing and the 8001 admin port use it). `XDMP-EXPNTREECACHEFULL` usually means the query pulls in too much data: rewrite the query first. More cache partitions mean more concurrent cache writers but less efficient ageing (p.48-50).
- **No global invalidation.** Caches are stand-aware, and stands are read-only, so updates never invalidate them (p.50).
- **Locks and timestamps are decentralised.** Each D-node locks its own documents; waiting transactions travel in the once-a-second heartbeat for deadlock detection. Timestamps are close to wall-clock time, so host clocks must agree. The distribute-timestamps option is `fast` by default (another host may briefly read stale data); `strict` makes updates wait until every host has the timestamp (p.50-51).
- **Forest choice on insert.** By default a URI maps deterministically through buckets to a forest, so concurrent writers contend on the same D-node lock. An "in-forest eval" or MLCP fastload skips the duplicate-URI check (p.54-55, 122).
- **MVCC mode.** `contemporaneous` (default) sees the newest timestamp but may wait for in-flight commits; `nonblocking` never waits but may be slightly behind, intended for app servers on a hot replica (p.109).

**Backup, failover, replication**
- **Backup.** Online; copies stand files, skipping identical files already in the target; requests halt only briefly at the end. Always back up the Security database too, because roles are numeric IDs (p.101).
- **Flash backup and Updates Allowed.** Forest states `all`, `delete-only`, `read-only` and `flash-backup` (retries changes until a retry timeout, default 120 s) let a snapshot be taken in a consistent on-disk state (p.101-102).
- **Journal archiving.** Streams the journal beside the backup for point-in-time recovery; the lag limit (15 s default) stalls database writes if the archive falls behind; archives grow without bound; only one backup receives archiving at a time; per-forest journals can leave a "jagged" restore, fixed with the Administrator's Guide script (p.102-103).
- **Incremental backup.** Saves changes found by scanning `Timestamps` files; `retain until backup` keeps deleted fragments for point-in-time recovery without journal archives (p.103-104).
- **Failover.** Heartbeat once a second; a host silent for the failover timeout (30 s default) is disconnected; failover needs a majority of hosts, so at least 3. E-node loss only needs the load balancer to route elsewhere (p.104-105).
- **Shared-disk.** Forests on a SAN, clustered file system or NFS, remotely mounted by one host at a time; the taker-over replays the journal like a restart; failover hosts need spare capacity; no automatic failback (restart the forest) (p.105-107).
- **Local-disk.** Replica forests are not byte-identical. Async replicating (bulk catch-up, no failover yet; primary writes capped to half the data sent) then sync replicating; commits are synchronous. Stripe replicas of a host's six primaries across at least two other hosts; ingest load doubles; also configure failover for Security, Modules, Triggers, Meters and Schemas (p.106-107).
- **Database replication.** Couple clusters, XDQP on port 7998, per forest by name, lag limit 15 s then the primary stalls, primary carries on if the replica cluster is down, replica can serve read-only queries. Keep index settings and the Security database aligned; failing over needs external coordination (DNS, load balancer, admin action) (p.107-108).
- **Flexible replication.** Asynchronous, trigger-based, document-level over HTTP with an optional filter; more overhead than journal replication; speed up with task-server threads, load-balanced targets and bandwidth (p.109-110).

**Rebalancing and tiers**
- **Rebalancing.** Triggered by adding or retiring forests, spreads documents evenly, moves them in delete-and-insert batches in one transaction, has a throttle. Always retire a forest before detaching and deleting it, or its content is lost (p.110-111, 113).
- **Assignment policies.** `bucket` (default, 16,000 buckets), `legacy` (moves much more data), `statistical` (least-full forest, non-deterministic, needs strict locking so MLCP fastload cannot be used, only rebalances past a threshold), `range` (tiered storage) (p.111-113 `[unverified — confirm for 11/12]`).
- **Tiered storage.** Partitions by range index value with their own storage; migrating whole forests is cheaper than rebalancing; partitions can go offline. Super-databases federate sub-databases, no updates through them, one level only (p.115-117).
- **S3.** Eventually consistent, so unsuitable for updates, journaling or shared-disk failover; fine for read-only forests, archive partitions and backups (p.118).

**Low-level settings (p.119-120)**
- Last-modified and directory-last-modified add a fragment write per update (off by default from MarkLogic 7); directory creation `manual` saves ingest work unless WebDAV or directory queries are used; locking `fast` (bucket and legacy) or `strict` (statistical and range), `off` only when URIs are certainly unique; journaling `strict`, `fast` or `off` (off only temporarily for a recoverable bulk load; strict is always used with shared-disk failover).
- Huge Pages at 3/8 of RAM and no Transparent Huge Pages; swap equal to RAM up to 32 GB RAM, otherwise 32 GB (the KB article behind `memory-and-os.md` gives a different formula; follow that note); the deadline I/O scheduler on Red Hat; several forests, because after merges a forest may be one stand with no internal parallelism.

**Clients and tools**
- MLCP imports 100 documents per batch and 10 batches per transaction by default; the book calls about 1,000 documents per transaction a good middle (p.121-122). XDBC is unencrypted unless SSL is layered on; XDBC over HTTP (`xcc.httpcompliant`, from MarkLogic 7) works through load balancers, which need session affinity for multi-statement transactions (p.64). SQL runs from memory over range-index views (p.65). SPARQL plans are searched by simulated annealing in a bounded time (p.98-99).

## Standard procedures

1. Name the layer the symptom lives in: index resolution, filtering, evaluator CPU, locking, merge or disk, cluster communication, backup, failover or replication, storage tier.
2. Slow search: run `xdmp:plan` for the constraints, compare `xdmp:estimate` with `fn:count` to see how many fragments are read and thrown away, check for `"unfiltered"`, and check that every range or typed predicate has a range index (p.19, 25-29).
3. Slow or failing updates: look for lock waits and deadlock restarts; check whether many requests write the same document or URI (modelling: one item per document), whether a query is running as an update, and whether a long multi-statement transaction holds locks (p.39-44).
4. Stale reads: check `distribute timestamps`, MVCC mode, host clock accuracy and whether the app server runs on a replica (p.51, 109).
5. Index change complaints: check reindex progress and throttle; remember the new index is unusable until it finishes (p.19).
6. Failover or quorum: count hosts, read heartbeat and failover timeouts, check replica state (async or sync replicating) and the spare capacity of the taking-over host (p.104-107).
7. Backup or restore: confirm the Security database is included, which backup holds journal archiving and its lag, jagged-restore risk, and flash-backup state (p.101-104).
8. After adding or removing forests: check the rebalancer, the assignment policy and locking mode, and that retired forests were retired before deletion (p.110-113).
9. Binaries: check the large size threshold, the large data directory location and E-node compressed tree cache for external binaries (p.46, 49).
10. State mechanism, evidence and fix, and tag every number or default `[unverified — confirm for 11/12]` unless checked.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --- | --- | --- | --- | --- |
| Range or typed predicate with no range index | Slow query, large candidate sets, high disk I/O | `xdmp:plan` shows no range constraint; `xdmp:estimate` far from the real result | Add the range index of the right type; reindex | Inside MarkLogic p.28-29 |
| Relying on filtering where indexes could resolve | Slow search that reads many documents then discards them | `xdmp:estimate` much higher than `fn:count` | Enable the index the query needs, or run unfiltered if false positives are tolerable | Inside MarkLogic p.14, 25-26 |
| Case- or diacritic-sensitive search without the fast index | Slow only for those searches | `xdmp:plan`; index settings | Enable fast case-sensitive or diacritic-sensitive searches if common | Inside MarkLogic p.67-68 |
| Frequent word with lost positions | Phrase or NEAR on a very common term slow or filtered | Non-empty `StopKeySet` file in a stand | Use word pairs, a narrower query, or revisit positions-list-max-size | Inside MarkLogic p.75 |
| Counting with `fn:count` at scale | Slow count pages | Code uses `fn:count` on a search | Use `xdmp:estimate` once indexes make it accurate | Inside MarkLogic p.25-26 |
| Many items packed in one large document | Lock contention, slow updates, whole-document rewrites | Many writers on one URI; deadlock restarts | One item per document, or fragmentation only when justified | Inside MarkLogic p.24-25, 41 |
| Query that is secretly an update | Slow, lock-heavy reads | Update function call or `xdmp:update` in code, or `declareUpdate()` in JS | Keep the query read-only; isolate the update in its own transaction | Inside MarkLogic p.40-41 |
| Long multi-statement transaction | Locks held, deadlock exceptions the client must retry | Transaction mode in code; retryable exception | Shorten it; the client must retry the whole sequence | Inside MarkLogic p.43-44 |
| Treating `XDMP-EXPNTREECACHEFULL` as a cache-size problem | Raising the cache does not help | Query returns or builds a huge tree | Rewrite the query to bring in less data | Inside MarkLogic p.49 |
| Zero expanded tree cache on D-nodes | Reindex or Admin 8001 problems on D-nodes | D-node group cache settings | Keep a small one (about 128 MB per the book) | Inside MarkLogic p.49 |
| Stale reads after a write on another host | Read-after-write misses within about a second | `distribute timestamps` fast; clock drift | Use `strict` where needed; fix clocks | Inside MarkLogic p.51 |
| App servers on a hot replica left on `contemporaneous` | Queries wait on in-flight replicated commits | MVCC setting on the replica's app server | Set `nonblocking` there | Inside MarkLogic p.109 |
| Point-in-time query after merges reclaimed old fragments | Old timestamp no longer queryable | Merge timestamp setting | Set the merge timestamp or retention before it is needed | Inside MarkLogic p.38-39 |
| Detaching and deleting a forest without retiring it | Documents gone | Forest was never retired | Retire first so content is redistributed | Inside MarkLogic p.111 |
| Statistical or range policy with fast locking or MLCP fastload | Duplicate-URI risk, fastload refused | Assignment policy and locking | Use strict locking; avoid fastload with these policies | Inside MarkLogic p.112, 119 |
| Backup without the Security database | Restored forests unreadable (numeric role IDs missing) | Backup contents | Always include Security (and Schemas) | Inside MarkLogic p.101 |
| Journal archive on slow storage with a low lag limit | Database writes stall | Lag limit; archive I/O | Raise the lag limit or speed the archive | Inside MarkLogic p.103 |
| Journal archiving never re-checkpointed | Huge archive, slow restore | Archive size; time since full backup | Take periodic full backups | Inside MarkLogic p.103 |
| Expecting automatic failback | Primary stays remote after recovery | Forest mount host | Restart the forest when ready to move it back | Inside MarkLogic p.105-106 |
| Failover hosts without spare capacity | Slowness or OOM after failover | Memory and disk of the failover host | Size for own plus failed-over forests; stripe replicas | Inside MarkLogic p.105-106 |
| Auxiliary databases without failover | Cluster impaired when their host fails | Failover config of Security, Modules, Triggers, Meters, Schemas | Configure failover for them too | Inside MarkLogic p.107 |
| Replica cluster index or Security config drift | Replica queries differ or fail | Compare database settings and Security | Keep index settings aligned; replicate Security | Inside MarkLogic p.108 |
| Putting S3 under updates, journals or shared-disk failover | Inconsistent reads, failed journaling | Storage location | Use S3 only for read-only forests, archives, backups | Inside MarkLogic p.118 |
| Last-modified and directory options left on after upgrade | Extra fragment writes on every update | Database settings | Turn off if not needed | Inside MarkLogic p.119 |
| Journaling `off` left on after a bulk load | Data loss on a crash | Journaling setting | Return to `fast` or `strict` | Inside MarkLogic p.120 |
| Transparent Huge Pages enabled | Memory stalls | `/sys/kernel/mm/transparent_hugepage/enabled`; ErrorLog advice | Disable; use configured Huge Pages | Inside MarkLogic p.120 |
| Multi-statement transactions through a load balancer without affinity | Transaction errors, partial work | LB config; XDBC over HTTP | Session affinity to one E-node | Inside MarkLogic p.64 |

## Sources

- "Inside MarkLogic Server", Jason Hunter and Mike Wooldridge, 3rd edition (MarkLogic 8, April 2016, 127 pp.), supplied by the maintainer as `Inside-MarkLogic-Server.pdf` (not stored in the repository; copyright MarkLogic). Page numbers above are the book's printed pages; the contents map is: what MarkLogic is p.5-11, indexing p.12-33, data management p.33-47, clustering and caching p.47-57, coding and connecting p.57-66, advanced text p.67-77, registered queries p.77-80, reverse index p.82-89, bitemporal p.90-94, semantics p.94-100, backups p.101-104, failover and replication p.104-110, rebalancing p.110-113, Hadoop p.113-114, tiered storage p.115-118, system control p.119-120.
- Related notes: `architecture.md`, `resource-consumption.md`, `databases-forests.md`, `ha-backup-failover.md`, `dr-scaling.md`, `memory-and-os.md`, `performance-tuning.md`.
