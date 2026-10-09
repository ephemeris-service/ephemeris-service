# -*- coding: utf-8 -*-
"""Batch interface against direct pyswisseph calls, synthetic inputs only."""
import json
import random
import struct
import unittest

import swisseph as swe

from ephemeris_service.core import BODIES, Engine
from tests.common import EPHE, Running

FL = swe.FLG_SWIEPH | swe.FLG_SPEED
NAMES = list(BODIES)
LAT, LON = 31.5, 121.25


def bits(x):
    return struct.pack("<d", x)


def req(times, names=None, flags=None, **extra):
    r = {"times": times, "bodies": names or NAMES, "flags": flags or ["SWIEPH", "SPEED"]}
    r.update(extra)
    return r


def with_place(times, **kw):
    return req(times, lat=LAT, lon=LON, house_system="P", **kw)


class BatchSynthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        swe.set_ephe_path(EPHE)
        cls.api = Running(Engine(EPHE))
        rng = random.Random(20261014)
        cls.times = [2378497.0, 2597641.0, 2451545.0, 2451545.0 + 1e-9, 2451545.0 + 1e-12,
                     2451545.0 + 2.5e-9, 2469807.123456789, 2440587.5, 2459580.25000000001]
        cls.times += [rng.uniform(2378497.0, 2597641.0) for _ in range(300)]
        cls.status, cls.out = cls.api.post("/v1/compute", with_place(cls.times))

    @classmethod
    def tearDownClass(cls):
        cls.api.close()

    def test_order_and_count(self):
        self.assertEqual(self.status, 200)
        rs = self.out["results"]
        self.assertEqual([r["jd_ut"] for r in rs], self.times)

    def test_values_bit_equal_to_direct_calls(self):
        for t, r in zip(self.times, self.out["results"]):
            for name in NAMES:
                xx, rf = swe.calc_ut(t, BODIES[name], FL)
                b = r["bodies"][name]
                got = (b["lon"], b["lat"], b["dist"], b["lon_speed"], b["lat_speed"], b["dist_speed"])
                for g, w in zip(got, xx):
                    self.assertEqual(bits(g), bits(w))
                self.assertEqual(b["retflag"], rf)
            cusps, ascmc = swe.houses(t, LAT, LON, b"P")
            h = r["houses"]
            want = list(cusps) + [ascmc[0], ascmc[1]]
            got = list(h["cusps"]) + [h["asc"], h["mc"]]
            self.assertEqual(len(h["cusps"]), 12)
            for a, b2 in zip(got, want):
                self.assertEqual(bits(a), bits(b2))

    def test_close_instants_not_rounded(self):
        rs = self.out["results"]
        lon = [rs[i]["bodies"]["月亮"]["lon"] for i in (2, 3, 4, 5)]
        self.assertNotEqual(lon[0], lon[1])
        self.assertNotEqual(lon[0], lon[3])
        self.assertNotEqual(lon[1], lon[3])
        # 2451545.0 + 1e-12 is the same double as 2451545.0
        self.assertEqual(2451545.0 + 1e-12, 2451545.0)
        self.assertEqual(lon[0], lon[2])

    def test_batch_equals_single_requests(self):
        for i, t in enumerate(self.times[:40]):
            _, one = self.api.post("/v1/compute", with_place([t]))
            self.assertEqual(one["results"][0], self.out["results"][i])

    def test_per_item_errors_do_not_affect_others(self):
        mixed = [2451545.0, 1.0e9, -1.0e9, "abc", None, True, 2451545.5, 5.0e6, 2378496.9, 2597641.1, 2451546.0]
        _, out = self.api.post("/v1/compute", with_place(mixed, names=NAMES[:3]))
        m = out["results"]
        codes = [x.get("error") for x in m]
        for i in (1, 2, 8, 9):
            self.assertEqual(codes[i], "OUT_OF_RANGE")
        for i in (3, 4, 5):
            self.assertEqual(codes[i], "INVALID_INPUT")
        for i in (0, 6, 10):
            _, one = self.api.post("/v1/compute", with_place([mixed[i]], names=NAMES[:3]))
            self.assertIsNone(m[i]["error"])
            self.assertEqual(m[i], one["results"][0])

    def test_polar_houses_undefined_positions_kept(self):
        _, out = self.api.post("/v1/compute", req([2451545.0, 2451546.0], NAMES[:2], lat=89.0, lon=0.0, house_system="P"))
        for x in out["results"]:
            self.assertEqual(x["houses"], {"ok": False, "error": "HOUSES_UNDEFINED"})
            self.assertTrue(x["bodies"][NAMES[0]]["ok"])

    def test_whole_request_invalid(self):
        cases = [json.dumps(req([2451545.0], NAMES[:1], flags=["SWIEPH"], extra_field="x")),
                 "{bad",
                 '{"times":[NaN],"bodies":["%s"],"flags":["SWIEPH"]}' % NAMES[0],
                 json.dumps(req([2451545.0], NAMES[:1], flags=["SPEED"])),
                 json.dumps(req([2451545.0], ["unknown"], flags=["SWIEPH"]))]
        for raw in cases:
            status, out = self.api.post("/v1/compute", None, raw=raw)
            self.assertEqual(status, 400)
            self.assertIn("INVALID_INPUT", json.dumps(out))

    def test_without_speed_flag(self):
        _, out = self.api.post("/v1/compute", req([2451545.0], NAMES[:1], flags=["SWIEPH"]))
        b = out["results"][0]["bodies"][NAMES[0]]
        xx, _ = swe.calc_ut(2451545.0, BODIES[NAMES[0]], swe.FLG_SWIEPH)
        self.assertNotIn("lon_speed", b)
        self.assertEqual(bits(b["lon"]), bits(xx[0]))


if __name__ == "__main__":
    unittest.main()
