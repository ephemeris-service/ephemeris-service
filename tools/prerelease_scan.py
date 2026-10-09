# -*- coding: utf-8 -*-
"""Pre-release scan: tracked files, file names and git history must carry no private material.

Usage: python tools/prerelease_scan.py [--terms FILE] [--history] [--authors]

Built-in checks (generic): absolute user-home paths, credential-like assignments and keys,
e-mail addresses (other than the reserved ".invalid" domain).
--terms FILE adds the caller's own vocabulary: one regular expression per line, '#' starts a comment.
The vocabulary is deliberately NOT stored in this repository; whoever releases supplies it.
--history also scans every version of every file and every commit message in all refs.
--authors prints author and committer identities found in history.
Exit status 1 when anything hits.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BUILTIN = {
    "absolute user-home path": r"[A-Za-z]:[\/]+Users[\/]|[/]Users[/]|[/]home[/][a-z]",
    "credential-like": r"(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{20,}",
    "e-mail address": r"[\w.+-]+@(?![\w.-]*\.invalid\b)[\w-]+\.[\w.-]+",
}


def load_terms(path):
    terms = {}
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            terms["term:%d" % n] = line
    return terms


def compile_patterns(extra=None):
    pats = dict(BUILTIN)
    pats.update(extra or {})
    return {k: re.compile(v, re.IGNORECASE) for k, v in pats.items()}


def git(*args):
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def scan_text(label, text, hits, compiled=None):
    compiled = compiled or compile_patterns()
    for n, line in enumerate(text.splitlines(), 1):
        for kind, rx in compiled.items():
            if rx.search(line):
                hits.append((kind, label, n, line.strip()[:120]))


def main(argv):
    extra = {}
    if "--terms" in argv:
        extra = load_terms(argv[argv.index("--terms") + 1])
    compiled = compile_patterns(extra)
    hits = []
    tracked = [p for p in git("ls-files", "-z").split(chr(0)) if p]
    for rel in tracked:
        scan_text("path:" + rel, rel, hits, compiled)
        if rel.endswith(".se1"):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            hits.append(("non-text file", rel, 0, ""))
            continue
        scan_text(rel, text, hits, compiled)
    if "--history" in argv:
        for c in git("rev-list", "--all").split():
            scan_text("commit-message:" + c[:8], git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", c), hits, compiled)
        scan_text("<git log -p, all refs>", git("log", "--all", "-p", "--format=", "--", ".", ":(exclude)*.se1"), hits, compiled)
        names = git("log", "--all", "--name-only", "--format=").splitlines()
        scan_text("<file names in history>", "\n".join(sorted(set(names))), hits, compiled)
    if "--authors" in argv:
        print("authors/committers in history:")
        print(git("log", "--all", "--format=%an <%ae> | %cn <%ce>").strip() or "(no commits yet)")
    for h in hits:
        print("HIT [%s] %s:%s: %s" % h)
    print("%d tracked files scanned, %d term(s) supplied, %d hit(s)" % (len(tracked), len(extra), len(hits)))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
