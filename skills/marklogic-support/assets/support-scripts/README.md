# Support scripts that are given to customers

These scripts are copied from Progress Knowledge Base articles so the engineer can hand the customer the exact file.
`pstack.sh` has **one deliberate change** from the article: `INTERVAL=5` instead of the article script's `INTERVAL=3`
(maintainer decision 2026-10-21; the article text says 5 seconds, but its script uses 3). A customer who downloads the
script from the KB article gets the 3-second version. To re-derive: `tests/test_support_scripts.py` pins the hash of the
original article script and the hash of this file, and a test proves that replacing `INTERVAL=5 TIME=$1` with
`INTERVAL=3 TIME=$1` reproduces the original, so the interval line is the only difference. Do not otherwise edit the
scripts. If the article changes, replace the file, update both hashes here and in `tests/test_support_scripts.py`, and
update this table.

| File | Source of truth | Copied |
| --- | --- | --- |
| `pstack.sh` | KB 000266816 "Creating a pstack movie for support" — https://community.progress.com/s/article/creating-a-pstack-movie-for-support (article dated Oct 15, 2024), with `INTERVAL=5` instead of `INTERVAL=3` | 2026-10-21, pasted by the maintainer (community pages cannot be fetched by the skill); interval changed 2026-10-21 |
| `exportMeters.xqy` | KB 000266887 "Exporting metering data" — https://community.progress.com/s/article/exporting-metering-data (article dated Oct 15, 2024). The URL is built from the article's URL Name `exporting-metering-data` and is not confirmed by the maintainer. | 2026-10-21 verbatim (no changes), pasted/saved by the maintainer (community pages cannot be fetched by the skill) |
| `get-raw.sh` | KB 000266887, as above | 2026-10-21 verbatim (no changes), pasted/saved by the maintainer |

Hashes (SHA-256): original KB script `7664a2c0e7d7e71e6ac7ba280391422b9b4ddaad13bf12182ae00701a400ab21`; this file `cbd5ad316f28a5e44d53d3da5b8f87633b97870eaecfbb9aa7aa79981d78a58c`.
`exportMeters.xqy` `ddcafdab21f1aea5dee8a879d8c5ec461bd142bd112e0df097cfee89bf229f97`; `get-raw.sh` `be0b593a8af7fd6935cfa259da7ad0d21c9696788a6ee4a8738ff5bbfd940440` (both verbatim, pinned in `tests/test_support_scripts.py`). If KB 000266887 changes, replace the files together with their hashes in the tests and this README.

## pstack.sh

Run as root on the MarkLogic host while the problem is happening: `./pstack.sh 60` records a stack trace of the MarkLogic
process every `INTERVAL=3` seconds for 60 seconds into `/tmp/<HHMMSS-MM-DD-YYYY>/pstack.log` and zips it to
`/tmp/<HHMMSS-MM-DD-YYYY>.zip`. Prerequisites (from the article): `yum -y install pstack sysstat psutils gdb`.

Things to know when sending it:

- **Interval:** this copy samples every 5 seconds (`INTERVAL=5`). The article text says 5 seconds but its own script uses 3, so a customer who downloads the KB copy gets 3-second samples.
- **MarkLogic version:** the script calls `/etc/MarkLogic/proc-util.sh pstack` (MarkLogic 11.3.1 and later, RHEL9-based builds).
  For earlier versions, or 11.3.x builds not based on RHEL9, the script's own comment says to replace that line with
  `service MarkLogic pstack >> /tmp/$TSTAMP/pstack.log`.
- **Impact:** pstack pauses the MarkLogic process while it records the threads, which has a performance impact.
- **`ml-support-dump.sh`:** the article also lists a "longer pstack script" said to collect OS-level information, but its
  listing is identical to `pstack.sh` (the maintainer confirmed the community site's copy is a duplicate too), so only
  `pstack.sh` is kept here and it is what customers use. Support dumps are usually generated separately or supplied through
  the telemetry link; OS-level data is requested with the SAR and host-metrics requests in
  `references/performance-data-requests.md`.
- **Alternative:** KB 000268341 "Using perf to understand performance" (https://community.progress.com/s/article/using-perf-to-understand-performance)
  samples instead of pausing the process; see the perf request in `references/performance-data-requests.md`.

## exportMeters.xqy and get-raw.sh (Meters export, KB 000266887)

Both give the raw metering XML files (the Monitoring History data) for a defined period, in place of a backup of the Meters database. The article says the exports can be reloaded into MarkLogic and used with the standard tools. A full Meters backup has all the data but is often very large and hard to transfer, so a time range is usually requested. Telemetry (MarkLogic 9+), when enabled, already sends metering data to Support; check it first. Otherwise Monitoring History must be enabled and have collected data for the incident time. The request text is in `references/performance-data-requests.md`.

### exportMeters.xqy

An XQuery script run in Query Console with the content database set to `Meters`. Four variables at the top are edited by the customer. Verified by reading the script:

- Defaults: `$start` `2018-03-15T00:00:00`; `$end` = `$start + P1D` (or give an exact dateTime); `$batch` 3000 (the comment says to lower it in case of expanded tree errors); `$output-dir` `/tmp`.
- It writes `meters-0.zip`, `meters-1.zip`, ... (one zip per `$batch` documents) with `xdmp:save`, so the files are written on the MarkLogic host that runs the query, and logs each file name to the ErrorLog (`writing <dir>/meters-<n>.zip`). Each save runs in its own transaction through `xdmp:invoke-function`.
- It selects documents with `cts:uris` where the element `{http://marklogic.com/manage/meters}start-time` is greater than `$start` and `end-time` is less than `$end`. Both comparisons are strict, and a document must lie wholly inside the window, so add a margin before and after the incident.
- Privileges: `xdmp:save` lists `http://marklogic.com/xdmp/privileges/xdmp-save` and `xdmp:invoke-function` lists `http://marklogic.com/xdmp/privileges/xdmp-invoke` (function pages); `xdmp:zip-create` lists none. Whether Query Console users need anything else was not tested `[unverified — confirm]`.

### get-raw.sh

A bash script that uses MLCP to export. Needs MLCP installed and an XDBC server on the port. Run as `./get-raw.sh <host> <user> <pass> "<start>" "<end>"`, for example `./get-raw.sh localhost admin admin "2018-04-12T00:00:00" "2018-04-14T00:00:00"` (times in the format `2018-03-14T00:00:00`). Verified by reading the script:

- Arguments in order: host, user, password, start, end. Port is fixed at 8000 (the script comment: the built-in server); edit the `port=` line for another XDBC server.
- Output directory `./meters-export` (relative to the current directory). The script comment says it should not exist beforehand; the MLCP export options page says `-output_file_path` "must not already exist".
- It writes the options file `.metrics` in the current directory (containing `-query_filter` and a JSON query on the `{http://marklogic.com/manage/meters}` elements `period` = `raw` and `period-start-time` greater than start and less than end), prints it, then runs `mlcp.sh export -database Meters -mode local -output_type archive -copy_permissions false -options_file .metrics`.
- `mlcp.sh` must be on the PATH; the script prepends `~/mlcp/bin` to it.
- Observation from reading the script: the password is passed with `-password` on the `mlcp.sh` command line, so it is visible in the process list on that machine. Customers may prefer a temporary account.
- MLCP options (MLCP 12 export options page, read 2026-10-21): `-mode` accepts `local`; `-output_type` is `document` or `archive`; `-copy_permissions` defaults to `true`; `-port` should have an XDBC App Server, default 8000; `-options_file` reads further options from a file. The page lists no required privileges or roles for the export user `[unverified — confirm]`.
