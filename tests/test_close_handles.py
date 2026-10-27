# -*- coding: utf-8 -*-
"""Swiss Ephemeris keeps open ephemeris files per thread and the server runs a thread per
connection, so every compute must close them before releasing the lock. Synthetic inputs only."""
import unittest

import swisseph as swe

from ephemeris_service.core import Engine
from tests.common import ALL_BODIES, EPHE, FLAGS


class CountingClose:
    """pyswisseph stand-in that counts close() calls."""

    def __init__(self):
        self.closed = 0

    def __getattr__(self, name):
        return getattr(swe, name)

    def close(self):
        self.closed += 1
        swe.close()


class ComputeClosesEphemeris(unittest.TestCase):
    REQ = {"times": [2451545.0, 2451545.5], "bodies": ALL_BODIES, "flags": FLAGS,
           "lat": 30.0, "lon": 120.0, "house_system": "P"}

    def test_closed_after_every_compute(self):
        stub = CountingClose()
        eng = Engine(EPHE, swe_module=stub)
        for n in (1, 2, 3):
            eng.compute(self.REQ)
            self.assertEqual(stub.closed, n)

    def test_closed_even_if_compute_raises(self):
        stub = CountingClose()
        eng = Engine(EPHE, swe_module=stub)

        def boom(*a, **k):
            raise RuntimeError("synthetic")
        eng._one_time = boom
        with self.assertRaises(RuntimeError):
            eng.compute(self.REQ)
        self.assertEqual(stub.closed, 1)


if __name__ == "__main__":
    unittest.main()
