# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tempfile
import unittest

from tests.common import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import prerelease_scan as ps  # noqa: E402


def run_scan(*args):
    # the child writes UTF-8 whatever the console code page is, and the output is decoded as UTF-8
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "tools/prerelease_scan.py", *args], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", env=env)


class PrereleaseScan(unittest.TestCase):
    def test_tracked_files_are_clean(self):
        r = run_scan()
        self.assertEqual(r.returncode, 0, r.stdout)


class ScannerCatchesThings(unittest.TestCase):
    """The scanner itself must fire on what it is meant to find (synthetic samples only)."""

    def test_builtin_patterns_fire(self):
        bs = chr(92)
        samples = {
            "absolute user-home path": "C:" + bs + "Us" + "ers" + bs + "someone",
            "credential-like": "pass" + "word = hunter2",
            "e-mail address": "write to someone" + "@example.org",
        }
        for kind, line in samples.items():
            hits = []
            ps.scan_text("x", line, hits)
            self.assertIn(kind, [h[0] for h in hits], line)

    def test_reserved_invalid_domain_is_allowed(self):
        hits = []
        ps.scan_text("x", "noreply@ephemeris-service.invalid", hits)
        self.assertEqual(hits, [])

    def test_ordinary_text_is_clean(self):
        hits = []
        ps.scan_text("x", "ordinary text about julian days and house cusps", hits)
        self.assertEqual(hits, [])

    def test_supplied_terms_fire_and_set_exit_status(self):
        with tempfile.TemporaryDirectory() as d:
            tf = os.path.join(d, "terms.txt")
            with open(tf, "w", encoding="utf-8") as f:
                f.write("# synthetic vocabulary\nephemeris\n")
            r = run_scan("--terms", tf)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("HIT [term:2]", r.stdout)
            with open(tf, "w", encoding="utf-8") as f:
                f.write("# nothing that occurs here\n" + "zzquux" + "zz\n")
            r = run_scan("--terms", tf)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_history_option_scans_history_and_prints_authors(self):
        with tempfile.TemporaryDirectory() as d:
            tf = os.path.join(d, "terms.txt")
            with open(tf, "w", encoding="utf-8") as f:
                f.write("Initial commit\n")
            r = run_scan("--terms", tf, "--history", "--authors")
            self.assertIn("authors/committers in history:", r.stdout)
            self.assertIn("HIT [term:1] commit-message:", r.stdout)
            self.assertEqual(r.returncode, 1, r.stdout)


if __name__ == "__main__":
    unittest.main()
