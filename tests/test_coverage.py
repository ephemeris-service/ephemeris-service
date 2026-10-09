# -*- coding: utf-8 -*-
"""The documented coverage bounds really are served from the bundled Swiss files."""
import unittest

import swisseph as swe

from ephemeris_service.core import BODIES, JD_MAX, JD_MIN
from tests.common import EPHE

F = swe.FLG_SWIEPH | swe.FLG_SPEED


class Coverage(unittest.TestCase):
    def test_bounds_are_served_by_swiss_files_for_every_body(self):
        swe.set_ephe_path(EPHE)
        for jd in (JD_MIN, JD_MIN + 1e-6, 2451545.0, JD_MAX - 1e-6, JD_MAX):
            for name, ipl in BODIES.items():
                _, rf = swe.calc_ut(jd, ipl, F)
                self.assertTrue(rf & swe.FLG_SWIEPH, (name, jd))

    def test_far_outside_is_not_swiss(self):
        swe.set_ephe_path(EPHE)
        for jd in (JD_MIN - 100.0, 2000000.0):
            _, rf = swe.calc_ut(jd, swe.SUN, F)
            self.assertFalse(rf & swe.FLG_SWIEPH)


if __name__ == "__main__":
    unittest.main()
