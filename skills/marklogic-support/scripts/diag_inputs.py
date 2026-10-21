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
    host_hint(source) -> str | None       stem of the nearest enclosing zip file name that is not generic, else the nearest enclosing folder
                                          name that is not generic and not a capture timestamp (HHMMSS-MM-DD-YYYY), else None. Generic
                                          (case-insensitive): 'pstack logs', 'pstack', 'perfdata', 'perf', 'logs', 'tmp', 'data', ''.
    close_all(sources)                    close the zip handles held by the sources.
    Source.label   human path chain, parts joined with ' > ', e.g. 'PSTACK Logs.zip > host61.zip > tmp/084321-09-21-2020/pstack.log'
    Source.parts   the chain components (a folder input gives the path relative to that folder as the single part)
    Source.name    basename of the last part;  Source.size  uncompressed size in bytes
    Source.head(n=65536) -> bytes;  Source.read() -> bytes (raises MemberTooLarge, a ValueError, above MAX_MEMBER);
    Source.sha256() -> hex digest (streamed in chunks).
    READ_ERRORS    tuple of the exceptions reading a Source can raise (OSError, ValueError, zipfile.BadZipFile, ...): catch them per source.

Skipped silently but counted in ONE note ('N macOS metadata file(s) skipped'): any path component `__MACOSX`, names starting `._`,
`.DS_Store`, `Thumbs.db`, `desktop.ini`. Zip directory entries are skipped without being counted. Symlinks in a folder are skipped
with a note.

Limits (plain module attributes, so tests can monkeypatch them): MAX_DEPTH = 3 zips nested; MAX_MEMBER = 512 MB per file or member;
MAX_TOTAL = 4 GB uncompressed over all zip members (reading stops with a note); MAX_MEMBERS = 50000 entries per zip (stops with a note);
RATIO_MIN_SIZE = 50 MB and RATIO = 200: a member bigger than RATIO_MIN_SIZE and RATIO times its compressed size is skipped.
Other notes: corrupt zip (BadZipFile), password-protected member, nesting deeper than MAX_DEPTH, member over MAX_MEMBER, unreadable file.
"""
import hashlib, io, os, re, zipfile, zlib
from pathlib import Path

MAX_DEPTH = 3
MAX_MEMBER = 512 * 1024 * 1024
MAX_TOTAL = 4 * 1024 ** 3
MAX_MEMBERS = 50000
RATIO_MIN_SIZE = 50 * 1024 * 1024
RATIO = 200
SEP = " > "
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
GENERIC = {"pstack logs", "pstack", "perfdata", "perf", "logs", "tmp", "data", ""}
TS_RE = re.compile(r"^\d{6}-\d\d-\d\d-\d{4}$")
CHUNK = 1024 * 1024
READ_ERRORS = (OSError, ValueError, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError)


class MemberTooLarge(ValueError):
    pass


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
        self.parts, self.size, self._open, self._holder = list(parts), size, opener, holder
        self.label = SEP.join(self.parts)
        self.name = self.parts[-1].rsplit("/", 1)[-1] if self.parts else ""

    def head(self, n=65536):
        with self._open() as f:
            return f.read(n)

    def read(self):
        with self._open() as f:
            data = f.read(MAX_MEMBER + 1)
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
        mparts = parts + [clean]
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
            try:
                with zf.open(info) as f:
                    data = f.read(MAX_MEMBER + 1)
                if len(data) > MAX_MEMBER:
                    st.notes.add(f"{label}: skipped, larger than {_mb(MAX_MEMBER)}")
                    continue
                inner = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                st.notes.add(f"{label}: not a readable zip file")
                continue
            except READ_ERRORS as e:
                st.notes.add(f"{label}: could not be read ({type(e).__name__})")
                continue
            h = _Zip(inner)
            _expand(inner, mparts, depth + 1, st, out, h)
            continue
        out.append(Source(mparts, info.file_size, (lambda zf=zf, info=info: zf.open(info)), holder))


def _open_zip_path(path, parts, st, out):
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        st.notes.add(f"{SEP.join(parts)}: not a readable zip file")
        return
    except OSError as e:
        st.notes.add(f"{SEP.join(parts)}: could not be read ({type(e).__name__})")
        return
    _expand(zf, parts, 1, st, out, _Zip(zf))


def _add_file(path, parts, st, out):
    is_zip = path.suffix.lower() == ".zip" or zipfile.is_zipfile(path)
    if is_zip:
        _open_zip_path(path, parts, st, out)
        return
    try:
        size = path.stat().st_size
    except OSError as e:
        st.notes.add(f"{SEP.join(parts)}: could not be read ({type(e).__name__})")
        return
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
        if p.is_dir():
            skipped_links = 0
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d != "__MACOSX")
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
                notes.add(f"{skipped_links} symbolic link(s) skipped in {p.name}")
        else:
            _add_file(p, [p.name], st, out)
    if st.junk:
        notes.add(f"{st.junk} macOS metadata file(s) skipped")
    return out


def _clean_stem(name):
    return re.sub(r"\.zip$", "", name.rsplit("/", 1)[-1], flags=re.I)


def host_hint(source):
    """Best-effort host name from the container names (see the module docstring), or None."""
    parts = source.parts
    for part in reversed(parts[:-1]):
        if part.lower().endswith(".zip"):
            stem = _clean_stem(part)
            if stem.lower() not in GENERIC:
                return stem
    for part in reversed(parts):
        for d in reversed(part.split("/")[:-1]):
            if d.lower() not in GENERIC and not TS_RE.match(d):
                return d
    return None


def dedupe(sources, notes):
    """Keep the first of byte-identical sources; one note per kept source that had copies."""
    seen, kept, dups = {}, [], {}
    for s in sources:
        key = (s.size, s.sha256())
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
