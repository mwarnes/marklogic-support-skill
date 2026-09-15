#!/usr/bin/env python3
"""Split a MarkLogic support dump and flag configuration issues.

Usage: parse_dump.py DUMP.txt [--out DIR]     (default DIR = dump-analysis/<DUMP stem>)
Writes: config/<host>/*.xml  status/*.txt  logs/<host>/*  logs/INVENTORY.md
        topology.json  summary.md  findings.md  logs/<host>/ERRORLOG-SUMMARY.md
"""
import argparse, json, re, shutil, sys
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- 1. sectioner
STRUCTURAL = {"Configuration", "Log Files", "Host Status"}
STATUS_GROUPS = ["App Server Status", "Database Topology", "Forest Status", "Trigger Definitions",
                 "CPF Domains", "CPF Pipelines", "FlexRep Domains", "SQL Schemas", "SQL Views",
                 "XML Schemas", "Host Status"]


def is_rule(l): return l.strip().startswith("=====")
def is_pct(l): return l.strip().startswith("%%%%")


def is_title_at(lines, i):
    return (i + 2 < len(lines) and is_rule(lines[i]) and is_rule(lines[i + 2])
            and not is_rule(lines[i + 1]) and lines[i + 1].strip() != "")


def iter_blocks(lines):
    """Yield ('header', dict, None) for %%% blocks, ('section', title, body_lines) for === title === blocks."""
    i, n, in_logs = 0, len(lines), False
    while i < n:
        if is_pct(lines[i]):
            j = i + 1
            while j < n and not is_pct(lines[j]): j += 1
            hdr = {}
            for l in lines[i + 1:j]:
                if ":" in l:
                    k, v = l.split(":", 1); hdr[k.strip()] = v.strip()
            yield "header", hdr, None
            in_logs, i = False, j + 1
            continue
        if is_title_at(lines, i):
            title = lines[i + 1].strip()
            if in_logs and "Logs/" not in title and title not in STRUCTURAL:
                i += 1; continue                     # a log line that merely looks like a title
            j = i + 2 if title.endswith(".xml") else i + 3   # <file>.xml shares its closing rule with "Validation results"
            while j < n and not is_pct(lines[j]):
                if is_title_at(lines, j):
                    t2 = lines[j + 1].strip()
                    if not in_logs or "Logs/" in t2 or t2 in STRUCTURAL: break
                j += 1
            in_logs = title == "Log Files" or (in_logs and title not in STRUCTURAL)
            yield "section", title, lines[i + 3:j]
            i = j
            continue
        i += 1


# ---------------------------------------------------------------- 2. splitter
def short(host): return (host or "unknown-host").split(".")[0]
def slug(s): return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")


def split(lines, out):
    """Write config/, status/, logs/ under out; return what the model needs."""
    res = {"header": {}, "hosts": [], "configs": defaultdict(dict), "validation": defaultdict(dict), "logs": []}
    host, pending_xml, status_group = None, None, None
    for kind, a, b in iter_blocks(lines):
        if kind == "header":
            hdr = a
            if "Report Host" in hdr: 
                res["header"] = hdr
                host = hdr["Report Host"]
            if "Hostname" in hdr: 
                host = hdr["Hostname"]
                res["hosts"].append(host)
            continue
        # kind == "section"
        title = a
        body = b
        if title in ("Configuration", "Log Files"): continue
        if title.endswith(".xml"): pending_xml = title; continue
        if title.startswith("Validation results") and pending_xml:
            text = "\n".join([l for l in (body or []) if not l.strip().startswith("#")]).strip() + "\n"
            res["configs"][host][pending_xml] = text
            res["validation"][host][pending_xml] = title.split(":", 1)[1].strip()
            p = out / "config" / short(host) / pending_xml
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
            pending_xml = None
            continue
        if "Logs/" in title:
            m = re.match(r"(?:file://([^/]+))?/.*?/Logs/(.+)$", title)
            if m:
                lhost, name = (m.group(1) or host), m.group(2)
                nonempty = sum(1 for l in body if l.strip())
                kept = nonempty > 1
                res["logs"].append({"host": short(lhost), "name": name, "lines": nonempty, "kept": kept})
                if kept:
                    p = out / "logs" / short(lhost) / name
                    p.parent.mkdir(parents=True, exist_ok=True); p.write_text("\n".join(body).strip() + "\n")
            continue
        if title in STATUS_GROUPS: status_group = title
        marker = f"{title}: {host}" if title == "Host Status" else title
        p = out / "status" / (slug(status_group or title) + ".txt")
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(f"### {marker}\n" + "\n".join(body).rstrip() + "\n\n")
    inv = ["# Log inventory", "", "| host | log | lines | kept |", "| --- | --- | --- | --- |"]
    inv += [f"| {l['host']} | {l['name']} | {l['lines']} | {'yes' if l['kept'] else 'skipped (placeholder)'} |"
            for l in res["logs"]]
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "logs" / "INVENTORY.md").write_text("\n".join(inv) + "\n")
    return res


# ---------------------------------------------------------------- 3. model
def strip_ns(text):
    return re.sub(r'\s(?:xmlns(?::\w+)?|xsi:schemaLocation)="[^"]*"', "", text)


def parse_xml(text, warnings, what):
    try:
        return ET.fromstring(strip_ns(text))
    except ET.ParseError as e:
        warnings.append(f"{what}: XML parse error: {e}"); return None


def txt(el, tag, default=None):
    x = el.find(tag) if el is not None else None
    return x.text.strip() if x is not None and x.text and x.text.strip() else default


def num(el, tag, default=0):
    try: return int(float(txt(el, tag, default)))
    except (TypeError, ValueError): return default


def build_model(res, dump_text):
    w = []
    m = {"warnings": w, "cluster": {}, "hosts": {}, "groups": {}, "appservers": [], "databases": {},
         "forests": {}, "host_status": {}, "forest_status": {}, "report": dict(res["header"])}
    cfg = res["configs"].get(res["hosts"][0]) if res["hosts"] else None
    cfg = cfg or next(iter(res["configs"].values()), {})
    roots = {f: parse_xml(t, w, f) for f, t in cfg.items()}

    r = roots.get("hosts.xml")
    for h in (r.findall("host") if r is not None else []):
        hid = txt(h, "host-id")
        name = txt(h, "host-name") or f"host-{hid}"
        if not txt(h, "host-name"): w.append(f"host {hid}: missing host-name, using {name}")
        m["hosts"][hid] = {"name": name, "group_id": txt(h, "group"), "zone": txt(h, "zone")}

    r = roots.get("groups.xml")
    for g in (r.findall("group") if r is not None else []):
        gid = txt(g, "group-id")
        name = txt(g, "group-name") or f"group-{gid}"
        if not txt(g, "group-name"): w.append(f"group {gid}: missing group-name, using {name}")
        m["groups"][gid] = {"name": name,
                            "list_cache": num(g, "list-cache-size"), "compressed_tree_cache": num(g, "compressed-tree-cache-size"),
                            "expanded_tree_cache": num(g, "expanded-tree-cache-size"), "triple_cache": num(g, "triple-cache-size"),
                            "failover_enable": txt(g, "failover-enable"), "host_timeout": num(g, "host-timeout"),
                            "host_names": [h["name"] for h in m["hosts"].values() if h["group_id"] == gid]}
        m["groups"][gid]["cache_sum"] = sum(m["groups"][gid][k] for k in ("list_cache", "compressed_tree_cache", "expanded_tree_cache", "triple_cache"))
        for kind in ("http", "xdbc", "odbc", "webdav"):
            for s in g.findall(f"{kind}-servers/{kind}-server"):
                m["appservers"].append({"name": txt(s, f"{kind}-server-name"), "kind": kind, "group_id": gid,
                                        "group_name": m["groups"][gid]["name"], "enabled": txt(s, "enabled"),
                                        "port": num(s, "port"), "root": txt(s, "root"), "database_id": txt(s, "database", "0"),
                                        "modules_id": txt(s, "modules", "0"), "authentication": txt(s, "authentication"),
                                        "default_user_id": txt(s, "default-user"), "request_timeout": num(s, "request-timeout"),
                                        "max_threads": num(s, "max-threads")})

    r = roots.get("assignments.xml")
    for a in (r.findall("assignment") if r is not None else []):
        fid = txt(a, "forest-id")
        name = txt(a, "forest-name") or f"forest-{fid}"
        if not txt(a, "forest-name"): w.append(f"forest {fid}: missing forest-name, using {name}")
        m["forests"][fid] = {"name": name, "host_id": txt(a, "host"), "enabled": txt(a, "enabled"),
                             "data_directory": txt(a, "data-directory"), "failover_enable": txt(a, "failover-enable"),
                             "replica_ids": [x.text for x in a.findall("forest-replicas/forest-replica")],
                             "failover_host_ids": [x.text for x in a.findall("failover-hosts/failover-host")]}

    r = roots.get("databases.xml")
    for d in (r.findall("database") if r is not None else []):
        did = txt(d, "database-id")
        name = txt(d, "database-name") or f"database-{did}"
        if not txt(d, "database-name"): w.append(f"database {did}: missing database-name, using {name}")
        m["databases"][did] = {"name": name, "forest_ids": [x.text for x in d.findall("forests/forest-id")],
                               "security_db_id": txt(d, "security-database", "0"), "schema_db_id": txt(d, "schema-database", "0"),
                               "triggers_db_id": txt(d, "triggers-database", "0"),
                               "reindexer_enable": txt(d, "reindexer-enable"), "reindexer_throttle": num(d, "reindexer-throttle"),
                               "rebalancer_enable": txt(d, "rebalancer-enable"), "assignment_policy": txt(d, "assignment-policy/assignment-policy-name"),
                               "directory_creation": txt(d, "directory-creation"), "locking": txt(d, "locking"),
                               "word_positions": txt(d, "word-positions"), "merge_max_size": num(d, "merge-max-size"),
                               "range_index_count": sum(len(d.findall(p)) for p in (
                                   "range-element-indexes/range-element-index", "range-element-attribute-indexes/range-element-attribute-index",
                                   "range-path-indexes/range-path-index", "range-field-indexes/range-field-index"))}

    r = roots.get("clusters.xml")
    if r is not None:
        m["cluster"] = {"name": txt(r, "cluster-name"), "id": txt(r, "cluster-id"), "effective_version": txt(r, "effective-version"),
                        "security_version": txt(r, "security-version"), "ssl_fips_enabled": txt(r, "ssl-fips-enabled"),
                        "bootstrap_host_ids": [x.text for x in r.findall("bootstrap-hosts/bootstrap-host")],
                        "foreign_clusters": len(r.findall("foreign-clusters/foreign-cluster"))}
    r = roots.get("keystore.xml")
    m["keystore"] = {"data_encryption": txt(r, "data-encryption"), "config_encryption": txt(r, "config-encryption"),
                     "logs_encryption": txt(r, "logs-encryption")} if r is not None else {}

    # status XML is embedded anywhere in the dump; grab by root tag
    for mm in re.finditer(r"<(host-status|forest-status)\b.*?</\1>", dump_text, re.S):
        el = parse_xml(mm.group(0), w, mm.group(1))
        if el is None: continue
        if mm.group(1) == "host-status":
            host_name = txt(el, "host-name")
            if host_name:  # skip entries with no host-name
                m["host_status"][host_name] = {
                    "version": txt(el, "version"), "os_version": txt(el, "os-version"), "cpus": num(el, "cpus"),
                    "memory_system_total": num(el, "memory-system-total"), "memory_size": num(el, "memory-size"),
                    "memory_system_free": num(el, "memory-system-free"), "memory_process_rss": num(el, "memory-process-rss"),
                    "data_dir_space": num(el, "data-dir-space")}
        else:
            forest_name = txt(el, "forest-name")
            if forest_name:  # skip entries with no forest-name
                # sizes/counts live on each <stand>; a forest-level element is used when present (synthetic dumps)
                stands = el.findall("stands/stand")
                stand_sum = lambda tag: num(el, tag) or sum(num(s, tag) for s in stands)
                m["forest_status"][forest_name] = {
                "state": txt(el, "state"), "host_id": txt(el, "host-id"), "disk_size": stand_sum("disk-size"),
                "memory_size": stand_sum("memory-size"), "journals_size": num(el, "journals-size"), "device_space": num(el, "device-space"),
                "stand_count": len(el.findall("stands/stand")), "reindexing": txt(el, "reindexing") == "true",
                "rebalancing": txt(el, "rebalancing") == "true",
                "document_count": num(el, "document-count") or sum(num(s, "document-count") for s in stands),
                "master_forest": txt(el, "master-forest")}

    # ---- resolve IDs to names
    hn = lambda i: m["hosts"].get(i, {}).get("name", i)
    dn = lambda i: m["databases"].get(i, {}).get("name") if i not in (None, "0") else None
    fn = lambda i: m["forests"].get(i, {}).get("name", i)
    replica_ids = {r for f in m["forests"].values() for r in f["replica_ids"]}
    db_of_forest = {fid: d["name"] for d in m["databases"].values() for fid in d["forest_ids"]}
    for fid, f in m["forests"].items():
        f.update(host_name=hn(f["host_id"]), replica_names=[fn(r) for r in f["replica_ids"]],
                 is_replica=fid in replica_ids, database_name=db_of_forest.get(fid),
                 status=m["forest_status"].get(f["name"], {}))
        if f["host_id"] not in m["hosts"]: w.append(f"forest {f['name']}: unknown host id {f['host_id']}")
    for d in m["databases"].values():
        d.update(forest_names=[fn(i) for i in d["forest_ids"]], security_db_name=dn(d["security_db_id"]),
                 schema_db_name=dn(d["schema_db_id"]), triggers_db_name=dn(d["triggers_db_id"]),
                 replica_count=sum(len(m["forests"].get(i, {}).get("replica_ids", [])) for i in d["forest_ids"]))
        for i in d["forest_ids"]:
            if i not in m["forests"]: w.append(f"database {d['name']}: unknown forest id {i}")
    for s in m["appservers"]:
        s.update(database_name=dn(s["database_id"]), modules_name=dn(s["modules_id"]) if s["modules_id"] != "0" else "(filesystem)")
    m["cluster"]["bootstrap_host_names"] = [hn(i) for i in m["cluster"].get("bootstrap_host_ids", [])]
    for h in m["hosts"].values():
        h.update(group_name=m["groups"].get(h["group_id"], {}).get("name", h["group_id"]), status=m["host_status"].get(h["name"], {}),
                 master_forests=[f["name"] for f in m["forests"].values() if f["host_name"] == h["name"] and not f["is_replica"]],
                 replica_forests=[f["name"] for f in m["forests"].values() if f["host_name"] == h["name"] and f["is_replica"]])
    return m


def write_summary(m, res, out):
    hdr, cl = m["report"], m["cluster"]
    ver = next((s.get("version") for s in m["host_status"].values() if s.get("version")), "?")
    L = [f"# Support dump summary", "",
         f"- Report time: {hdr.get('Report Time', '?')} · scope: {hdr.get('Report Scope', '?')} · report host: {hdr.get('Report Host', '?')}",
         f"- MarkLogic {ver} · cluster **{cl.get('name')}** · effective-version {cl.get('effective_version')} · bootstrap {', '.join(cl.get('bootstrap_host_names', []))} · foreign clusters {cl.get('foreign_clusters', 0)}",
         f"- {len(m['hosts'])} hosts · {len(m['groups'])} groups · {len(m['appservers'])} app servers · {len(m['databases'])} databases · {len(m['forests'])} forests ({sum(f['is_replica'] for f in m['forests'].values())} replicas)",
         f"- Encryption at rest: data={m.get('keystore', {}).get('data_encryption')} config={m.get('keystore', {}).get('config_encryption')} logs={m.get('keystore', {}).get('logs_encryption')}",
         ""]
    if m["warnings"]: L += ["## Warnings", ""] + [f"- {x}" for x in m["warnings"]] + [""]
    L += ["## Hosts", "", "| host | zone | group | CPUs | RAM MB | ML RSS MB | data-dir free MB | master forests | replica forests |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for h in m["hosts"].values():
        s = h["status"]
        L.append(f"| {short(h['name'])} | {h['zone']} | {h['group_name']} | {s.get('cpus', '?')} | {s.get('memory_system_total', '?')} | {s.get('memory_process_rss', '?')} | {s.get('data_dir_space', '?')} | {len(h['master_forests'])} | {len(h['replica_forests'])} |")
    L += ["", "## Groups", "", "| group | hosts | list | CTC | ETC | triple | cache sum MB | failover | host-timeout |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for g in m["groups"].values():
        L.append(f"| {g['name']} | {len(g['host_names'])} | {g['list_cache']} | {g['compressed_tree_cache']} | {g['expanded_tree_cache']} | {g['triple_cache']} | {g['cache_sum']} | {g['failover_enable']} | {g['host_timeout']} |")
    L += ["", "## App servers", "", "| name | kind | group | port | auth | default-user id | content db | modules | root |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in sorted(m["appservers"], key=lambda s: s["port"]):
        L.append(f"| {s['name']} | {s['kind']} | {s['group_name']} | {s['port']} | {s['authentication']} | {s['default_user_id']} | {s['database_name'] or '**none (0)**'} | {s['modules_name']} | {s['root']} |")
    L += ["", "## Databases", "", "| database | forests | replicas | security / schemas / triggers | range idx | positions | dir-creation | reindexer / throttle | rebalancer | locking |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in m["databases"].values():
        L.append(f"| {d['name']} | {len(d['forest_ids'])} | {d['replica_count']} | {d['security_db_name']} / {d['schema_db_name']} / {d['triggers_db_name']} | {d['range_index_count']} | {d['word_positions']} | {d['directory_creation']} | {d['reindexer_enable']} / {d['reindexer_throttle']} | {d['rebalancer_enable']} | {d['locking']} |")
    L += ["", "## Forests by host", ""]
    for h in m["hosts"].values():
        items = []
        for f in m["forests"].values():
            if f["host_name"] != h["name"]: continue
            st = f["status"]
            items.append(f"{f['name']}{' [replica]' if f['is_replica'] else ''} ({f['database_name'] or 'unattached'}; {st.get('state', '?')}, {st.get('disk_size', '?')} MB, {st.get('stand_count', '?')} stands{', REINDEXING' if st.get('reindexing') else ''})")
        L += [f"### {short(h['name'])}", ""] + [f"- {x}" for x in items] + [""]
    (out / "summary.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- 4. checks
def F(sev, check, component, message, evidence, reference, row):
    return {"severity": sev, "check": check, "component": component, "message": message,
            "evidence": evidence, "reference": reference, "row": row}


def group_failover_on(m): return any(g["failover_enable"] == "true" for g in m["groups"].values())


def chk_failover_no_replica(m):
    out = []
    for f in m["forests"].values():
        if (f["failover_enable"] == "true" and group_failover_on(m) and f["database_name"]
                and not f["replica_ids"] and not f["failover_host_ids"] and not f["is_replica"]):
            out.append(F("medium", "failover-no-replica", f"forest {f['name']}",
                         f"failover enabled but no replica forest or failover host; database {f['database_name']} on {short(f['host_name'])} is unavailable if that host fails",
                         "assignments.xml: forest-replicas and failover-hosts empty", "ha-backup-failover.md",
                         "Failover enabled on DB but no replica forests / failover hosts"))
    return out


def chk_replica_same_host(m):
    out = []
    for f in m["forests"].values():
        for rid in f["replica_ids"]:
            r = m["forests"].get(rid)
            if r and r["host_id"] == f["host_id"]:
                out.append(F("high", "replica-same-host", f"forest {f['name']}",
                             f"replica {r['name']} is on the same host ({short(f['host_name'])}) as its master — failover cannot protect it",
                             "assignments.xml: master host == replica host", "ha-backup-failover.md", "Replica forest on same host as master"))
    return out


def chk_even_host_count(m):
    n = len(m["hosts"])
    if n and n % 2 == 0:
        return [F("high" if n == 2 else "medium", "even-host-count", "cluster",
                  f"{n} hosts: losing one host {'loses quorum (2-host cluster cannot fail over)' if n == 2 else 'leaves an even split; quorum needs >50% of hosts online'}",
                  "hosts.xml host count", "cluster-hosts-groups.md", "Even number of hosts / 2-node cluster, one host down")]
    return []


def chk_cache_vs_ram(m):
    out = []
    for g in m["groups"].values():
        rams = [m["host_status"].get(h, {}).get("memory_system_total") or 0 for h in g["host_names"]]
        rams = [r for r in rams if r]
        if not rams:
            out.append(F("low", "cache-vs-ram", f"group {g['name']}", "cannot evaluate: no Host Status memory data in dump", "-", "memory-and-os.md", "Group cache sizes summed exceed host RAM")); continue
        ratio = g["cache_sum"] / min(rams)
        if ratio > 0.5:
            out.append(F("high", "cache-vs-ram", f"group {g['name']}",
                         f"group caches total {g['cache_sum']} MB = {ratio:.0%} of the smallest member host RAM ({min(rams)} MB); leaves too little for range indexes, OS and other processes",
                         "groups.xml cache sizes vs host-status memory-system-total", "memory-and-os.md",
                         "Group cache sizes summed exceed host RAM (esp. after adding a small host to a group of large ones)"))
        elif ratio > 1 / 3:
            out.append(F("low", "cache-vs-ram", f"group {g['name']}", f"group caches total {g['cache_sum']} MB = {ratio:.0%} of smallest host RAM ({min(rams)} MB) — at the upper end of the 1/3–1/2 guidance [unverified — confirm]",
                         "groups.xml vs host-status", "memory-and-os.md", "Group cache sizes summed exceed host RAM"))
    return out


def chk_forests_per_host(m):
    out = []
    for h in m["hosts"].values():
        s, n = h["status"], len(h["master_forests"])
        if not s: 
            out.append(F("low", "forests-per-host", f"host {short(h['name'])}", f"{n} master forests; cannot evaluate against CPU/RAM (no Host Status)", "-", "memory-and-os.md", "Too many forests for host RAM/vCPU")); continue
        by_cpu, by_ram = max(1, s.get("cpus", 0) // 2), max(1, s.get("memory_system_total", 0) // 8192)
        if n > by_cpu or n > by_ram:
            out.append(F("medium", "forests-per-host", f"host {short(h['name'])}",
                         f"{n} master forests (+{len(h['replica_forests'])} replicas) on {s.get('cpus')} CPUs / {s.get('memory_system_total')} MB RAM; guidance ≈2 vCPU + 8 GB per forest → ~{min(by_cpu, by_ram)} forests",
                         "assignments.xml vs host-status cpus/memory-system-total", "memory-and-os.md", "Too many forests for host RAM/vCPU"))
    return out


def chk_appserver_no_db(m):
    return [F("medium", "appserver-no-db", f"app server {s['name']}",
              f"{s['kind']} server on port {s['port']} has database=0 (no content database); modules={s['modules_name']} — verify intent",
              "groups.xml <database>0</database>", "app-servers.md", "Content database and modules database swapped after environment clone")
            for s in m["appservers"] if s["database_id"] == "0" and s["kind"] != "webdav"]


def chk_app_level_auth(m):
    return [F("low", "app-level-auth-default-user", f"app server {s['name']}",
              f"authentication=application-level on port {s['port']}: every request runs as default-user id {s['default_user_id']}; verify in the Security database that this user has least privilege (users are not in the dump)",
              "groups.xml authentication/default-user", "app-servers.md", "Application-level auth with default user `admin` or privileged role")
            for s in m["appservers"] if s["authentication"] == "application-level"]


def chk_dir_creation(m):
    webdav_dbs = {s["database_id"] for s in m["appservers"] if s["kind"] == "webdav"}
    return [F("low", "dir-creation-automatic", f"database {d['name']}",
              "directory-creation=automatic on a database not served by a WebDAV server; creates directory fragments on every insert",
              "databases.xml directory-creation", "databases-forests.md", "Directory creation set to `automatic` for high-volume ingest")
            for did, d in m["databases"].items() if d["directory_creation"] == "automatic" and did not in webdav_dbs]


def chk_reindexer_throttle(m):
    out = []
    for d in m["databases"].values():
        active = [n for n in d["forest_names"] if m["forest_status"].get(n, {}).get("reindexing")]
        if d["reindexer_throttle"] == 5 and active:
            out.append(F("medium", "reindexer-throttle-5", f"database {d['name']}",
                         f"reindexing in progress on {len(active)} forest(s) ({', '.join(active[:5])}) with reindexer-throttle=5 (maximum) — competes with queries for I/O",
                         "databases.xml reindexer-throttle; forest-status reindexing=true", "databases-forests.md",
                         "Reindex kicked off during peak hours with reindexer throttle 5"))
    return out


def chk_forest_oversize(m):
    return [F("medium", "forest-oversize", f"forest {n}", f"forest is {s['disk_size'] / 1024:.0f} GB on disk (> 512 GB rule of thumb)",
              "forest-status disk-size", "databases-forests.md", "Forest grown past ~512 GB (rule of thumb)")
            for n, s in m["forest_status"].items() if s["disk_size"] > 512 * 1024]


def chk_disk_headroom(m):
    out = []
    for h in m["hosts"].values():
        sts = [m["forest_status"][f] for f in h["master_forests"] + h["replica_forests"] if f in m["forest_status"]]
        if not sts: continue
        largest, free = max(s["disk_size"] for s in sts), min(s["device_space"] for s in sts)
        if largest and free < 1.5 * largest:
            out.append(F("high", "disk-headroom", f"host {short(h['name'])}",
                         f"free device space {free} MB is below 1.5× the largest forest ({largest} MB); merges may fail (XDMP-FORESTNOSPACE)",
                         "forest-status device-space vs disk-size", "databases-forests.md", "Insufficient free disk for merges"))
    return out


def chk_orphans(m):
    out = [F("low", "orphan-forest", f"forest {f['name']}", f"forest on {short(f['host_name'])} is not attached to any database and is not a replica",
             "assignments.xml vs databases.xml forests", "databases-forests.md", "Deleting forest still attached to database")
           for f in m["forests"].values() if not f["database_name"] and not f["is_replica"]]
    out += [F("low", "empty-database", f"database {d['name']}", "database has no forests attached", "databases.xml <forests/>",
              "databases-forests.md", "Single forest for large database (no parallelism)") for d in m["databases"].values() if not d["forest_ids"]]
    return out


def chk_encryption(m):
    k = m.get("keystore", {})
    if k.get("data_encryption") in ("default-on", "on"):
        return [F("low", "encryption-on", "keystore", f"encryption at rest is {k['data_encryption']} for data — confirm the keystore/KMS keys are backed up; data is unrecoverable without them",
                  "keystore.xml data-encryption", "security.md", "Encryption-at-rest enabled without key export/backup")]
    return []


def chk_config_drift(m, res):
    out = []
    norm = lambda t: re.sub(r'\stimestamp="[^"]*"', "", t)
    hosts = list(res["configs"])
    for f in sorted({f for c in res["configs"].values() for f in c} - {"server.xml"}):  # server.xml is per-host (host-id, licence) by design
        texts = {h: norm(res["configs"][h][f]) for h in hosts if f in res["configs"][h]}
        if len(set(texts.values())) > 1:
            out.append(F("medium", "config-drift", f"config {f}", f"{f} differs between hosts {', '.join(short(h) for h in texts)} — cluster config should be identical on every host",
                         "diff config/<host>/" + f, "cluster-hosts-groups.md", "Version mismatch during rolling upgrade held too long"))
    return out


CHECKS = [chk_failover_no_replica, chk_replica_same_host, chk_even_host_count, chk_cache_vs_ram, chk_forests_per_host,
          chk_appserver_no_db, chk_app_level_auth, chk_dir_creation, chk_reindexer_throttle, chk_forest_oversize,
          chk_disk_headroom, chk_orphans, chk_encryption]
SEV = {"high": 0, "medium": 1, "low": 2}


def run_checks(m, res):
    findings = [f for c in CHECKS for f in c(m)] + chk_config_drift(m, res)
    return sorted(findings, key=lambda f: (SEV[f["severity"]], f["check"], f["component"]))


def write_findings(findings, out):
    L = ["# Findings", "", f"{len(findings)} finding(s): " + ", ".join(f"{n} {s}" for s, n in sorted(Counter(f['severity'] for f in findings).items(), key=lambda x: SEV[x[0]])) or "none", "",
         "| Severity | Check | Component | Message | Evidence | Reference |", "| --- | --- | --- | --- | --- | --- |"]
    L += [f"| {f['severity']} | {f['check']} | {f['component']} | {f['message']} | {f['evidence']} | {f['reference']} — row: {f['row']} |" for f in findings]
    (out / "findings.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- 5. ErrorLog summary
LOG_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) (\w+): (.*)$")
CODE_RE = re.compile(r"\b((?:XDMP|SVC|SEC|ADMIN|REST|RESTAPI|X509|OI|XDQP|SQL|TRGR|CPF|FLEXREP|JS|XSLT|SSL|MANAGE|SEARCH|PKG|OPTIC|DBG|TS|ICN|RDT|TDE|SER|XSD|XI)-[A-Z0-9]+)\b")


def summarise_errorlog(path):
    levels, codes, restarts, first, last, total = Counter(), {}, [], None, None, 0
    with path.open(errors="replace") as fh:
        for line in fh:
            mm = LOG_RE.match(line.rstrip("\n"))
            if not mm: continue
            ts, lvl, msg = mm.groups(); total += 1
            levels[lvl] += 1; first = first or ts; last = ts
            if "Starting MarkLogic Server" in msg: restarts.append(ts)
            for c in set(CODE_RE.findall(msg)):
                d = codes.setdefault(c, {"count": 0, "first": ts, "last": ts, "sample": msg[:160]})
                d["count"] += 1; d["last"] = ts
    L = [f"## {path.name}", "", f"- {total} log lines · {first} → {last}", f"- Restarts: {len(restarts)}" + (f" ({', '.join(restarts[:5])}{'…' if len(restarts) > 5 else ''})" if restarts else ""), "",
         "| Level | Lines |", "| --- | --- |"] + [f"| {l} | {n} |" for l, n in levels.most_common()]
    L += ["", "| Code | Count | First | Last | Sample |", "| --- | --- | --- | --- | --- |"]
    L += [f"| {c} | {d['count']} | {d['first']} | {d['last']} | {d['sample'].replace('|', '/')} |"
          for c, d in sorted(codes.items(), key=lambda x: -x[1]["count"])[:15]]
    return "\n".join(L) + "\n\n"


def write_errorlog_summaries(out):
    for host_dir in sorted(p for p in (out / "logs").iterdir() if p.is_dir()):
        logs = sorted(host_dir.glob("*ErrorLog*.txt"))
        if logs:
            (host_dir / "ERRORLOG-SUMMARY.md").write_text(f"# ErrorLog summary — {host_dir.name}\n\n" + "".join(summarise_errorlog(p) for p in logs))


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    dump = Path(a.dump)
    out = Path(a.out) if a.out else Path("dump-analysis") / dump.stem
    for sub in ("config", "status", "logs"): 
        try: shutil.rmtree(out / sub)
        except FileNotFoundError: pass
    out.mkdir(parents=True, exist_ok=True)
    try:
        text = dump.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError) as e:
        print(f"Error reading {dump}: {e}", file=sys.stderr)
        return 1
    lines = text.split("\n")
    res = split(lines, out)
    model = build_model(res, text)
    (out / "topology.json").write_text(json.dumps(model, indent=1, default=str))
    write_summary(model, res, out)
    findings = run_checks(model, res)
    write_findings(findings, out)
    write_errorlog_summaries(out)
    if res["header"].get("Report Scope", "cluster") != "cluster":
        print(f"WARNING: Report Scope is {res['header'].get('Report Scope')!r}, expected 'cluster'", file=sys.stderr)
    print(f"wrote {out}: {len(res['configs'])} host config sets, "
          f"{sum(l['kept'] for l in res['logs'])}/{len(res['logs'])} logs kept, {len(model['hosts'])} hosts, {len(model['forests'])} forests, {len(findings)} findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())