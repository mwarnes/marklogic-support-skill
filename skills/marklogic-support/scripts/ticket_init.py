#!/usr/bin/env python3
"""Create a MarkLogic support ticket working directory and its audit trail.

Usage: ticket_init.py TICKET [--root DIR] [--check]
Creates <root>/<TICKET>/audit-trail/ with Timeline.md, Analysis.md, Required-Diagnostics.md,
Problems.md and Root-Cause.md (a title line each) when they do not exist; existing files are never
touched. <root> defaults to the git top-level directory of the current directory, else the current
directory. Prints the ticket directory and the audit-trail file names.
With --check nothing is created: it lists an existing ticket's audit trail, or exits 1 if the ticket
(or its audit-trail directory) does not exist.
"""
import argparse, re, subprocess, sys
from pathlib import Path

FILES = ["Timeline", "Analysis", "Required-Diagnostics", "Problems", "Root-Cause"]
TICKET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
RESERVED_RE = re.compile(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?", re.I)    # Windows device names


def project_root(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except OSError:
        pass
    return Path(cwd)


def check_id(ticket):
    if (not TICKET_RE.fullmatch(ticket) or ".." in ticket or ticket.endswith(".")
            or RESERVED_RE.fullmatch(ticket)):
        sys.exit(f"ticket_init: invalid ticket id {ticket!r} (use letters, digits, '.', '_' and '-' only)")


def check(ticket, root):
    check_id(ticket)
    trail = Path(root) / ticket / "audit-trail"
    if not trail.is_dir():
        sys.exit(f"ticket_init: ticket {ticket} not found under {root} (no audit-trail/ directory)")
    return trail.parent, sorted(p.name for p in trail.iterdir())


def init(ticket, root):
    check_id(ticket)
    trail = Path(root) / ticket / "audit-trail"
    try:
        trail.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            f = trail / f"{name}.md"
            if not f.exists():
                f.write_text(f"# {name}\n\n")
        return trail.parent, sorted(p.name for p in trail.iterdir())
    except OSError as e:
        sys.exit(f"ticket_init: cannot create the audit trail under {root}: {e.strerror or e}"
                 + (f" ({e.filename})" if e.filename else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticket")
    ap.add_argument("--root")
    ap.add_argument("--check", action="store_true", help="list an existing ticket; never create anything")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else project_root(Path.cwd())
    ticket_dir, names = (check if a.check else init)(a.ticket, root)
    print(ticket_dir)
    print("\n".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
