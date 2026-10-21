"""Shared input walker for the diagnostic analysis scripts (analyse_pstack.py, analyse_perf.py): files, folders, zips and zips in zips.

Nothing is ever extracted to disk: zip members are read in memory, member names are used only for labels (so a `../` name cannot
write anywhere), and labels have leading '/' and '..' / '.' components dropped.

Use (each script must put this folder on sys.path first, so it works under `python3 -I` and from any directory):
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import diag_inputs
    notes = set()
    sources = diag_inputs.dedupe(diag_inputs.walk(paths, notes), notes)   # walk raises FileNotFoundError for a missing path
    for s in sources: s.label, s.name, s.size, s.parts, diag_inputs.host_hint(s), s.head(), s.read()
    diag_inputs.close_all(sources)                                          # optional: closes zip handles (also closed on garbage collection)

API
    walk(paths, notes) -> list[Source]    files are sources; folders are walked recursively in sorted order; a `.zip` (by suffix or by
                                          `zipfile.is_zipfile`) is expanded in place, including zips inside zips up to MAX_DEPTH (the inner
                                          zip is read into memory, limit MAX_MEMBER). `notes` is a set of one-line strings, never customer
                                          text beyond the label of the container.
    dedupe(sources, notes) -> list        keeps the first of byte-identical sources (sha256 + size); one note per kept source:
                                          'N duplicate copy(ies) of <label> skipped'.
    host_hint(source) -> str | None       walks the chain components innermost first (the folders of the file, then the zip stem and the folders
                                          of each enclosing zip member, then the outer names), skips generic names and capture timestamps
                                          (HHMMSS-MM-DD-YYYY) and returns the first remaining one, else None, so `ticket.zip > hostA/pstack.log`
                                          gives hostA and `ticket.zip > host61.zip > tmp/<ts>/pstack.log` gives host61. Generic (case-
                                          insensitive): 'pstack logs', 'pstack', 'perfdata', 'perf', 'logs', 'tmp', 'data', ''. The result is passed
                                          through safe_label.
    safe_label(text, limit=200) -> str    untrusted text made safe for one line of markdown, a table cell or a note: C0/C1 control characters and
                                          DEL become '?', '|' becomes '/', a backtick becomes "'", whitespace runs collapse to one space, and text
                                          over `limit` is cut with an ellipsis; Unicode format/unassigned/private-use characters are dropped and an empty result is '?'. Every label, host hint and header string goes through it.
    slug(text, limit=60) -> str           directory-name slug of an input name ([A-Za-z0-9._-] only, else 'analysis').
    csv_cell(value)                       a str cell that starts with = + - @ TAB or CR gets a leading "'" (spreadsheet formula injection); the bare
                                          placeholder '-' and non-str values are left as they are.
    disambiguate(rows)                    rows with the same 'host' (case-insensitive) get ' (<tail of the last label part, 30 chars>)' appended.
    print_notes(notes)                    the Notes to stderr (used before an error exit).
    close_all(sources)                    close the zip handles held by the sources.
    Source.label   human path chain, parts joined with ' > ', e.g. 'PSTACK Logs.zip > host61.zip > tmp/084321-09-21-2020/pstack.log'
    Source.parts   the chain components (a folder input gives the path relative to that folder as the single part)
    Source.name    basename of the last part;  Source.size  uncompressed size in bytes
    Source.head(n=65536) -> bytes;  Source.read() -> bytes (raises MemberTooLarge, a ValueError, above MAX_MEMBER);
    Source.sha256() -> hex digest (streamed in chunks).
    READ_ERRORS    tuple of the exceptions reading a Source can raise (OSError, ValueError, zipfile.BadZipFile, ...): catch them per source.

Skipped silently but counted in ONE note ('N macOS metadata file(s) skipped'): any path component `__MACOSX` (the files inside a pruned
`__MACOSX` folder are counted too, so a zip and its unzipped folder give the same count), names starting `._`, `.DS_Store`, `Thumbs.db`,
`desktop.ini`. Zip directory entries are skipped without being counted. Symlinks in a folder are skipped with a note. Anything that is not a
regular file (FIFO, socket, device) is never opened: it is counted in ONE note 'N special file(s) skipped'. A file without a `.zip` suffix is a
zip only when it starts with the local-file magic PK\x03\x04 (a text log with a zip appended is read as text).

Limits (plain module attributes, so tests can monkeypatch them): MAX_DEPTH = 3 zips nested; MAX_MEMBER = 512 MB per file or member;
MAX_TOTAL = 4 GB: the sum of the declared uncompressed sizes of the zip members accepted so far, counting an inner zip's own size AND its
members (loose files in folders and top-level files are NOT counted; reading stops with a note); NESTED_BUDGET = 1 GiB of inner zips held in
memory at once (an inner zip that would exceed it is skipped with a note; an inner zip with no usable members is released);
MAX_MEMBERS = 50000 entries per zip: the entry count declared in the end-of-central-directory record (zip64 too) is checked BEFORE the zip is
opened and a zip over the limit is skipped with a note (if the record cannot be read, the entry list is cut at MAX_MEMBERS instead);
RATIO_MIN_SIZE = 50 MB and RATIO = 200: a member bigger than RATIO_MIN_SIZE and RATIO times its compressed size is skipped.
Other notes: corrupt zip (BadZipFile), password-protected member, nesting deeper than MAX_DEPTH, member over MAX_MEMBER, unreadable file,
a source that cannot be hashed (kept, never treated as a duplicate).
Memory: logs are read and parsed whole in memory, so a very large log (hundreds of MB) can need several GB of RAM `[unverified — confirm]`.
"""
import hashlib, io, os, re, stat, struct, sys, unicodedata, zipfile, zlib
from pathlib import Path

MAX_DEPTH = 3
MAX_MEMBER = 512 * 1024 * 1024
MAX_TOTAL = 4 * 1024 ** 3
MAX_MEMBERS = 50000
NESTED_BUDGET = 1024 ** 3
RATIO_MIN_SIZE = 50 * 1024 * 1024
RATIO = 200
SEP = " > "
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
GENERIC = {"pstack logs", "pstack", "perfdata", "perf", "logs", "tmp", "data", "",
           # folder names of the customer diagnostics guide layout (hosts/<hostname>/pstack|perf|sar|OSLogs|Logs ...)
           "hosts", "oslogs", "sar", "meters", "monitoring", "performance", "repro", "dump", "cloud", "backups"}
ENV_NAMES = {"prod", "production", "qa", "uat", "stage", "staging", "dev", "test", "preprod", "dr"}
TS_RE = re.compile(r"^\d{6}-\d\d-\d\d-\d{4}$")
CHUNK = 1024 * 1024
READ_ERRORS = (OSError, ValueError, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError)


class MemberTooLarge(ValueError):
    pass


_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SPACE_RE = re.compile(r"\s+")
_DROP_CATS = frozenset(("Cf", "Cn", "Co", "Cs"))
_SLUG_BAD_RE = re.compile(r"[^A-Za-z0-9._-]")


def safe_label(text, limit=200):
    """Untrusted text made safe for one markdown line / table cell / note (see the module docstring)."""
    t = _CTRL_RE.sub("?", str(text)).replace("|", "/").replace("`", "'")
    t = "".join(c for c in t if unicodedata.category(c) not in _DROP_CATS)
    t = _SPACE_RE.sub(" ", t).strip() or "?"
    return t if len(t) <= limit else t[:max(limit - 1, 0)] + "\u2026"


def csv_cell(value):
    """Neutralise spreadsheet formula injection: a str starting with = + - or @ (other than the bare placeholder '-') gets a leading quote."""
    if isinstance(value, str) and value != "-" and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def slug(text, limit=60):
    """A directory-name slug: only [A-Za-z0-9._-], repeats collapsed, leading dots/underscores stripped, capped, 'analysis' when empty."""
    t = re.sub(r"_+", "_", _SLUG_BAD_RE.sub("_", str(text))).lstrip("._")
    return t[:limit] or "analysis"


def disambiguate(rows):
    """Append ' (<tail of the last label part>)' to the 'host' of rows whose host (case-insensitive) is shared; rows are dicts with host and label."""
    count = {}
    for r in rows:
        count[r["host"].lower()] = count.get(r["host"].lower(), 0) + 1
    for r in rows:
        if count[r["host"].lower()] > 1:
            last = r["label"].split(SEP)[-1]
            r["host"] = f"{r['host']} ({last if len(last) <= 30 else chr(0x2026) + last[-29:]})"


def print_notes(notes, file=None):
    """The Notes (the reasons inputs were skipped) to stderr, before an error exit."""
    if notes:
        print("Notes:", file=file or sys.stderr)
        for n in sorted(notes):
            print(f"- {n}", file=file or sys.stderr)


def _mb(n):
    return f"{n / 1048576:g} MB"


def _clean(name):
    """Label-safe version of a path inside a zip: forward slashes, no leading '/', no '.' or '..' components."""
    return "/".join(p for p in name.replace("\\", "/").split("/") if p not in ("", ".", ".."))


def _is_junk(name):
    parts = name.replace("\\", "/").split("/")
    return "__MACOSX" in parts or any(p.startswith("._") or p.lower() in JUNK_NAMES for p in parts if p)


class _Zip:
    """A zip held open for its members (from a path or from bytes in memory)."""
    def __init__(self, zf):
        self.zf = zf

    def close(self):
        try:
            self.zf.close()
        except Exception:
            pass

    def __del__(self):
        self.close()


class Source:
    def __init__(self, parts, size, opener, holder=None):
        self.parts, self.size, self._open, self._holder = [safe_label(p) for p in parts], size, opener, holder
        self.label = SEP.join(self.parts)
        self.name = self.parts[-1].rsplit("/", 1)[-1] if self.parts else ""

    def head(self, n=65536):
        with self._open() as f:
            return f.read(n)

    def read(self):
        want = min(self.size, MAX_MEMBER) + 1
        with self._open() as f:
            data = f.read(want)
            if len(data) >= want:       # at least size+1 bytes: the declared size is too small or over the limit; go on in chunks
                chunks, n = [data], len(data)
                while n <= MAX_MEMBER:
                    c = f.read(min(CHUNK, MAX_MEMBER + 1 - n))
                    if not c:
                        break
                    chunks.append(c); n += len(c)
                data = b"".join(chunks)
        if len(data) > MAX_MEMBER:
            raise MemberTooLarge(f"{self.label}: larger than {_mb(MAX_MEMBER)}")
        return data

    def sha256(self):
        h = hashlib.sha256()
        with self._open() as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()

    def __repr__(self):
        return f"Source({self.label!r}, {self.size})"


class _State:
    def __init__(self, notes):
        self.notes, self.junk, self.total, self.holders, self.stopped = notes, 0, 0, [], False
        self.special, self.nested = 0, 0


def _declared_entries(tail):
    """Total entry count from the end-of-central-directory record found in `tail` (the last bytes of a zip), zip64 aware; None on any doubt."""
    try:
        i = tail.rfind(b"PK\x05\x06")
        if i < 0 or len(tail) < i + 22:
            return None
        total = struct.unpack_from("<H", tail, i + 10)[0]
        if total == 0xFFFF:
            j = tail.rfind(b"PK\x06\x06", 0, i)
            if j < 0 or len(tail) < j + 40:
                return None
            total = struct.unpack_from("<Q", tail, j + 32)[0]
        return total
    except Exception:
        return None


TAIL = 64 * 1024 + 22


def _too_many_entries(tail, parts, st):
    n = _declared_entries(tail)
    if n is not None and n > MAX_MEMBERS:
        st.notes.add(f"{SEP.join(parts)}: stopped reading, more than {MAX_MEMBERS} entries")
        return True
    return False


def _expand(zf, parts, depth, st, out, holder):
    infos = list(zf.infolist())
    if len(infos) > MAX_MEMBERS:
        st.notes.add(f"{SEP.join(parts)}: stopped reading, more than {MAX_MEMBERS} entries")
        infos = infos[:MAX_MEMBERS]
    for info in sorted(infos, key=lambda i: i.filename):
        if st.stopped:
            return
        if info.is_dir() or info.filename.endswith("/"):
            continue
        if _is_junk(info.filename):
            st.junk += 1
            continue
        clean = _clean(info.filename)
        if not clean:
            continue
        mparts = parts + [safe_label(clean)]
        label = SEP.join(mparts)
        if info.flag_bits & 0x1:
            st.notes.add(f"{label}: skipped, password-protected")
            continue
        if info.file_size > MAX_MEMBER:
            st.notes.add(f"{label}: skipped, larger than {_mb(MAX_MEMBER)}")
            continue
        if info.file_size > RATIO_MIN_SIZE and info.file_size > RATIO * max(info.compress_size, 1):
            st.notes.add(f"{label}: skipped, suspicious compression ratio")
            continue
        if st.total + info.file_size > MAX_TOTAL:
            st.notes.add(f"{SEP.join(parts)}: stopped reading, more than {_mb(MAX_TOTAL)} uncompressed in total")
            st.stopped = True
            return
        st.total += info.file_size
        try:
            is_zip = clean.lower().endswith(".zip")
            if not is_zip and info.file_size >= 22:
                with zf.open(info) as f:
                    is_zip = f.read(4) == b"PK\x03\x04"
        except READ_ERRORS:
            is_zip = False
        if is_zip:
            if depth >= MAX_DEPTH:
                st.notes.add(f"{label}: not opened, zips nested more than {MAX_DEPTH} deep")
                continue
            if st.nested + info.file_size > NESTED_BUDGET:
                st.notes.add(f"{label}: skipped, nested zips over {_mb(NESTED_BUDGET)} in memory")
                continue
            try:
                with zf.open(info) as f:
                    data = f.read(MAX_MEMBER + 1)
                if len(data) > MAX_MEMBER:
                    st.notes.add(f"{label}: skipped, larger than {_mb(MAX_MEMBER)}")
                    continue
                if _too_many_entries(data[-TAIL:], mparts, st):
                    continue
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                st.notes.add(f"{label}: not a readable zip file")
                continue
            except READ_ERRORS as e:
                st.notes.add(f"{label}: could not be read ({type(e).__name__})")
                continue
            h = _Zip(inner)
            held = len(data)
            st.nested += held
            before = len(out)
            _expand(inner, mparts, depth + 1, st, out, h)
            if len(out) == before:       # nothing usable inside: release the bytes
                h.close(); st.nested -= held
            continue
        out.append(Source(mparts, info.file_size, (lambda zf=zf, info=info: zf.open(info)), holder))


def _tail_of(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - TAIL))
            return f.read(TAIL)
    except OSError:
        return b""


def _open_zip_path(path, parts, st, out):
    if _too_many_entries(_tail_of(path), parts, st):
        return
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        st.notes.add(f"{SEP.join(parts)}: not a readable zip file")
        return
    except OSError as e:
        st.notes.add(f"{SEP.join(parts)}: could not be read ({type(e).__name__})")
        return
    _expand(zf, parts, 1, st, out, _Zip(zf))


def _starts_with_zip_magic(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"PK\x03\x04" and zipfile.is_zipfile(path)
    except OSError:
        return False


def _add_file(path, parts, st, out):
    parts = [safe_label(p) for p in parts]
    try:
        sr = os.stat(path)
    except OSError as e:
        st.notes.add(f"{SEP.join(parts)}: could not be read ({type(e).__name__})")
        return
    if not stat.S_ISREG(sr.st_mode):       # FIFO, socket, device: never opened
        st.special += 1
        return
    if path.suffix.lower() == ".zip" or _starts_with_zip_magic(path):
        _open_zip_path(path, parts, st, out)
        return
    size = sr.st_size
    if size > MAX_MEMBER:
        st.notes.add(f"{SEP.join(parts)}: skipped, larger than {_mb(MAX_MEMBER)}")
        return
    out.append(Source(parts, size, lambda path=path: open(path, "rb")))


def walk(paths, notes):
    """Sources for the given files, folders and zips; raises FileNotFoundError(path) for a missing path. See the module docstring."""
    st, out = _State(notes), []
    for p in map(Path, paths):
        if not os.path.lexists(p):
            raise FileNotFoundError(2, "path not found", str(p))
        try:
            mode = os.stat(p).st_mode
        except OSError as e:
            notes.add(f"{safe_label(p.name)}: could not be read ({type(e).__name__})")
            continue
        if stat.S_ISDIR(mode):
            skipped_links = 0
            for root, dirs, files in os.walk(p):
                keep = []
                for d in sorted(dirs):
                    if d == "__MACOSX":
                        st.junk += sum(len(fs) for _, _, fs in os.walk(os.path.join(root, d)))
                    else:
                        keep.append(d)
                dirs[:] = keep
                for f in sorted(files):
                    fp = Path(root) / f
                    rel = fp.relative_to(p).as_posix()
                    if _is_junk(rel):
                        st.junk += 1
                    elif fp.is_symlink():
                        skipped_links += 1
                    else:
                        _add_file(fp, [rel], st, out)
            if skipped_links:
                notes.add(f"{skipped_links} symbolic link(s) skipped in {safe_label(p.name)}")
        else:
            _add_file(p, [p.name], st, out)
    if st.junk:
        notes.add(f"{st.junk} macOS metadata file(s) skipped")
    if st.special:
        notes.add(f"{st.special} special file(s) skipped")
    return out


def _clean_stem(name):
    return re.sub(r"\.zip$", "", name.rsplit("/", 1)[-1], flags=re.I)


def _chain(source):
    """Container names of a source, outermost first: folders, zip member folders and zip stems."""
    chain = []
    parts = source.parts
    for i, part in enumerate(parts):
        pieces = part.split("/")
        chain += pieces[:-1]
        if i < len(parts) - 1:             # a zip member name: its stem is a component too
            chain.append(_clean_stem(pieces[-1]))
    return chain


def host_hint(source):
    """Best-effort host name from the container names (see the module docstring), or None."""
    for comp in reversed(_chain(source)):
        if comp.lower() not in GENERIC and not TS_RE.match(comp):
            return safe_label(comp)
    return None


def environments(sources):
    """Distinct environment-looking folder names (Prod, QA, Stage ...) in the sources' paths, first spelling, in order of appearance."""
    seen = {}
    for src in sources:
        for comp in _chain(src):
            if comp.lower() in ENV_NAMES:
                seen.setdefault(comp.lower(), comp)
    return list(seen.values())


def dedupe(sources, notes):
    """Keep the first of byte-identical sources; one note per kept source that had copies."""
    seen, kept, dups = {}, [], {}
    for s in sources:
        try:
            key = (s.size, s.sha256())
        except READ_ERRORS as e:
            notes.add(f"{s.label}: could not be hashed ({type(e).__name__}); not checked for duplicates")
            kept.append(s)
            continue
        if key in seen:
            dups[id(seen[key])] = dups.get(id(seen[key]), 0) + 1
        else:
            seen[key] = s
            kept.append(s)
    for s in kept:
        if id(s) in dups:
            notes.add(f"{dups[id(s)]} duplicate copy(ies) of {s.label} skipped")
    return kept


def close_all(sources):
    for s in sources:
        if s._holder is not None:
            s._holder.close()
