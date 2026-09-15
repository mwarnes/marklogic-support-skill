# MarkLogic query performance tuning and optimization

## Concepts

- **Unfiltered vs filtered search**: The most common MarkLogic performance mistake. Unfiltered search resolves entirely from indexes (fast), filtered search loads and validates actual document content (slow). By default, cts:search is filtered. Unfiltered search is only available with explicit `"unfiltered"` option, trades accuracy for speed, includes false positives from phrase searches with 3+ words, wildcard searches, and case/punctuation sensitivity.

- **Range indexes, lexicons, positions indexes**: Core mechanisms enabling unfiltered search. Range indexes enable fast range queries; lexicons enable fast value lookups; positions indexes enable fast phrase/near queries by tracking word positions. When these indexes are missing, queries must filter (scan all matching documents). See `databases-forests.md` for configuration, this file focuses on their performance role.

- **xdmp:query-meters and xdmp:query-trace**: Primary tools for diagnosing slow query behavior. `xdmp:query-meters` provides timing breakdown and cache hit/miss statistics. `xdmp:query-trace` logs detailed query evaluation steps to ErrorLog.txt, showing which XPath steps are "unsearchable" and require filtering.

- **Profiler API**: Evaluates XQuery/JavaScript request performance beyond search operations. Functions include `prof:enable`, `prof:eval`, `prof:report` for detailed execution timing and resource usage analysis. Requires profiling enabled on App Server.

- **MarkLogic caches for query tuning**: Three caches impact query performance: list cache (search term lists), compressed tree cache (compressed XML on disk), expanded tree cache (uncompressed XML in memory). Cache hit rates in `xdmp:query-meters` output indicate optimization opportunities. Cache sizing/capacity planning is handled in `memory-and-os.md`, this file focuses on interpreting cache behavior during performance tuning.

- **Efficient cts:query construction**: Compose constraints directly into `cts:query` expressions (e.g., `cts:and-query`) rather than retrieving broad result sets and filtering in XQuery/JavaScript afterward. The search APIs (`cts:search`, `cts:element-values`) use indexes for fast performance when queries are properly structured.

## Standard procedures

1. **Run xdmp:query-meters on slow query**: Append `xdmp:query-meters()` to query and examine elapsed time and cache hit/miss ratios. Record results for comparison across runs.

2. **Use xdmp:query-trace for detailed analysis**: Add `xdmp:query-trace(true())` before query execution. Check ErrorLog.txt for "unsearchable" XPath steps indicating filtering requirements.

3. **Check filtered vs unfiltered search behavior**: For `cts:search` calls, compare performance with and without `"unfiltered"` option to identify filtering overhead.

4. **Verify index configuration**: Check database configuration for range indexes, lexicons, and positions indexes that match query constraints. Missing indexes force filtered search.

5. **Profile with Profiler API**: Enable profiling on App Server, use `prof:enable(xdmp:request())` followed by `prof:report()` for detailed execution analysis beyond search operations.

6. **Analyze cache statistics**: In `xdmp:query-meters` output, high cache miss ratios indicate disk I/O bottlenecks; cross-reference with cache sizing in `memory-and-os.md`.

## Common mistakes & symptoms

| Mistake | Symptom seen by customer | How to confirm | Fix / best practice | Source |
| --------- | --------------------------- | ---------------- | --------------------- | --------- |
| Missing range index for range constraint | Slow range queries, high filtering overhead | `xdmp:query-trace` shows "unsearchable" range step; `xdmp:query-meters` shows high filtering time | Add appropriate range index to database configuration; reindex if needed | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| Missing positions index for phrase/near queries | Slow phrase searches, `cts:near-query` performance issues | `xdmp:query-trace` shows phrase/near operations requiring filtering; check database "word positions" setting disabled | Enable "word positions" in database configuration; note increased storage overhead | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| Post-filtering results in XQuery/JS instead of cts:query composition | Poor performance despite proper indexes | Code retrieves broad `cts:search` results, then filters with XQuery predicates; `xdmp:query-meters` shows high fragment/document access | Compose constraints into `cts:and-query`/`cts:or-query`; let indexes filter, not application code | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| Overly broad cts:search scope | High fragment access, slow queries despite indexes | `xdmp:query-meters` shows large fragments processed; query searches all documents when subset needed | Narrow query with collection constraints, directory filters, or additional cts:query elements | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| Diagnosing without query-meters/query-trace | Guesswork, incorrect optimization attempts | Performance complaints without measurement data | Always run `xdmp:query-meters` and `xdmp:query-trace` before proposing fixes | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/query_meters.html> |
| Realizing unbounded result sequence | Memory pressure, XDMP-TREECACHEFULL exception | Large result sets loaded entirely into memory; expanded tree cache full | Avoid queries returning entire database (batch/paginate results), rewrite query more efficiently, ensure swap space configured, add memory, or raise cache sizes (temporary fix) | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |
| Low cache hit rates ignored | Disk I/O bottleneck, erratic query performance | `xdmp:query-meters` shows high cache misses on list/tree caches | Cross-reference cache sizing with `memory-and-os.md`; consider cache allocation adjustments | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/query_meters.html> |
| Filtered search when unfiltered sufficient | Unnecessary validation overhead | `"unfiltered"` option not tested; application can tolerate approximate results for fragment-root/top-level searches, single-term/simple queries | Use `cts:search` with `"unfiltered"` for deep pagination or when false positives acceptable | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/unfiltered.html> |
| Complex query without step-by-step analysis | Cannot isolate performance bottleneck | Monolithic query with poor performance | Break query into components, measure each with `xdmp:query-meters` to isolate slow parts | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/query_meters.html> |
| Missing lexicon for unique value queries | Slow `cts:element-values` or distinct value operations | Query scans all documents for value extraction | Configure a range index on the element/attribute to enable a value lexicon for fast unique-value lookups and counts (`cts:element-values`, `xdmp:element-values`) | <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html> |

## Sources

- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/perftune.html>
- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/query_meters.html>
- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/profile.html>
- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/unfiltered.html>
- <https://docs.progress.com/bundle/marklogic-server-tune-query-performance-12/page/topics/status.html>
