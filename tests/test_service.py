# -*- coding: utf-8 -*-
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr

import swisseph as swe

from ephemeris_service.core import (BODIES, ERROR_CODES, JD_MAX, JD_MIN, Engine, EpheIntegrityError)
from tests.common import (ALL_BODIES, EPHE, FLAGS, REPO, SYN_PLACES, SYN_TIMES, Exploding, ForcedMoshier,
                          Running, temp_ephe_copy)

SW = swe.FLG_SWIEPH | swe.FLG_SPEED


def req(times, bodies=None, place=None, flags=None):
    r = {"times": times, "bodies": bodies or ALL_BODIES, "flags": flags or FLAGS}
    if place is not None:
        r.update({"lat": place[0], "lon": place[1], "house_system": "P"})
    return r


class BitExact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        swe.set_ephe_path(EPHE)
        cls.engine = Engine(EPHE)
        cls.api = Running(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.api.close()

    def test_service_equals_direct_pyswisseph_bit_for_bit(self):
        for place in SYN_PLACES:
            status, out = self.api.post("/v1/compute", req(SYN_TIMES, place=place))
            self.assertEqual(status, 200)
            self.assertEqual(len(out["results"]), len(SYN_TIMES))
            for jd, item in zip(SYN_TIMES, out["results"]):
                self.assertEqual(item["jd_ut"].hex(), jd.hex())
                self.assertIsNone(item["error"])
                for name in ALL_BODIES:
                    xx, rf = swe.calc_ut(jd, BODIES[name], SW)
                    b = item["bodies"][name]
                    self.assertTrue(b["ok"], (name, b))
                    got = [b["lon"], b["lat"], b["dist"], b["lon_speed"], b["lat_speed"], b["dist_speed"]]
                    self.assertEqual([v.hex() for v in got], [v.hex() for v in xx], name)
                    self.assertEqual(b["retflag"], rf)
                cusps, ascmc = swe.houses(jd, place[0], place[1], b"P")
                h = item["houses"]
                self.assertTrue(h["ok"])
                self.assertEqual([v.hex() for v in h["cusps"]], [v.hex() for v in cusps])
                self.assertEqual(h["asc"].hex(), ascmc[0].hex())
                self.assertEqual(h["mc"].hex(), ascmc[1].hex())

    def test_order_follows_request(self):
        times = [SYN_TIMES[3], SYN_TIMES[1], SYN_TIMES[5]]
        _, out = self.api.post("/v1/compute", req(times, bodies=["冥王星", "太阳"]))
        self.assertEqual([r["jd_ut"] for r in out["results"]], times)
        self.assertEqual(list(out["results"][0]["bodies"]), ["冥王星", "太阳"])

    def test_no_speed_flag_drops_speed_fields(self):
        _, out = self.api.post("/v1/compute", req([SYN_TIMES[3]], bodies=["太阳"], flags=["SWIEPH"]))
        b = out["results"][0]["bodies"]["太阳"]
        self.assertTrue(b["ok"])
        self.assertNotIn("lon_speed", b)
        self.assertEqual(b["lon"].hex(), swe.calc_ut(SYN_TIMES[3], swe.SUN, swe.FLG_SWIEPH)[0][0].hex())

    def test_json_roundtrip_is_exact(self):
        # awkward doubles: shortest-repr serialisation must restore the same bits
        times = [2451545.0 + k * 0.1234567890123 for k in range(50)]
        _, out = self.api.post("/v1/compute", req(times, bodies=["月亮"]))
        for jd, item in zip(times, out["results"]):
            self.assertEqual(item["jd_ut"].hex(), jd.hex())
            self.assertEqual(item["bodies"]["月亮"]["lon"].hex(), swe.calc_ut(jd, swe.MOON, SW)[0][0].hex())

    def test_julday_revjul(self):
        _, a = self.api.post("/v1/julday", {"year": 2000, "month": 1, "day": 1, "hour": 12.0})
        self.assertEqual(a["jd_ut"].hex(), swe.julday(2000, 1, 1, 12.0).hex())
        _, b = self.api.post("/v1/julday", {"year": 1500, "month": 3, "day": 4, "hour": 6.5, "calendar": "julian"})
        self.assertEqual(b["jd_ut"].hex(), swe.julday(1500, 3, 4, 6.5, 0).hex())
        _, c = self.api.post("/v1/revjul", {"jd_ut": 2451545.123})
        y, m, d, h = swe.revjul(2451545.123)
        self.assertEqual((c["year"], c["month"], c["day"], c["hour"].hex()), (y, m, d, h.hex()))
        status, e = self.api.post("/v1/julday", {"year": 2000, "month": 13, "day": 1, "hour": 0})
        self.assertEqual((status, e["error"]), (400, "INVALID_INPUT"))

    def test_health_and_version(self):
        self.assertEqual(self.api.get("/health"), (200, {"status": "ok"}))
        status, v = self.api.get("/version")
        self.assertEqual(status, 200)
        self.assertEqual(v["ephemeris"]["swisseph_version"], swe.version)
        self.assertEqual(v["error_codes"], list(ERROR_CODES))
        self.assertEqual(self.api.get("/nope")[0], 404)


class ErrorCodes(unittest.TestCase):
    """All six codes, each triggered at least once; one failing item never spoils the others."""

    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(EPHE)
        cls.api = Running(cls.engine)
        cls.seen = set()

    @classmethod
    def tearDownClass(cls):
        cls.api.close()

    def _codes(self, item):
        found = {item["error"]} if item.get("error") else set()
        for b in item.get("bodies", {}).values():
            if not b["ok"]:
                found.add(b["error"])
        if "houses" in item and not item["houses"]["ok"]:
            found.add(item["houses"]["error"])
        self.seen |= found
        return found

    def test_invalid_input_one_time_does_not_spoil_others(self):
        good = SYN_TIMES[3]
        _, out = self.api.post("/v1/compute", req([good, "abc", None, True, good + 1]), None) \
            if False else self.api.post("/v1/compute", req([good, "abc", None, True, good + 1], place=(10.0, 20.0)))
        r = out["results"]
        self.assertEqual(self._codes(r[1]), {"INVALID_INPUT"})
        self.assertEqual(self._codes(r[2]), {"INVALID_INPUT"})
        self.assertEqual(self._codes(r[3]), {"INVALID_INPUT"})
        for ok_item in (r[0], r[4]):
            self.assertEqual(self._codes(ok_item), set())
        self.assertEqual(r[0]["bodies"]["太阳"]["lon"].hex(), swe.calc_ut(good, swe.SUN, SW)[0][0].hex())

    def test_invalid_input_location_only_spoils_houses(self):
        _, out = self.api.post("/v1/compute", req([SYN_TIMES[3]], place=(95.0, 20.0)))
        item = out["results"][0]
        self.assertEqual(item["houses"], {"ok": False, "error": "INVALID_INPUT"})
        self.assertTrue(all(b["ok"] for b in item["bodies"].values()))
        self._codes(item)

    def test_invalid_input_whole_request(self):
        for bad in ({}, {"times": [1.0]}, req([2451545.0], bodies=["不存在"]), req([2451545.0], flags=["SPEED"]),
                    dict(req([2451545.0]), chart_id="x"), dict(req([2451545.0]), purpose="scan")):
            status, out = self.api.post("/v1/compute", bad)
            self.assertEqual((status, out), (400, {"error": "INVALID_INPUT"}), bad)
        # house system outside the closed set
        _, out = self.api.post("/v1/compute", dict(req([2451545.0]), lat=1.0, lon=1.0, house_system="K"))
        self.assertEqual(out["results"][0]["houses"], {"ok": False, "error": "INVALID_INPUT"})
        # NaN / Infinity / garbage are not JSON for us
        for raw in ('{"times":[NaN],"bodies":["太阳"],"flags":["SWIEPH"]}', "not json", "[1,2]"):
            status, out = self.api.post("/v1/compute", None, raw=raw)
            self.assertEqual((status, out), (400, {"error": "INVALID_INPUT"}), raw)
        self.seen.add("INVALID_INPUT")

    def test_out_of_range(self):
        ts = [JD_MIN - 1.0, SYN_TIMES[3], JD_MAX + 1.0, 1721423.5]
        _, out = self.api.post("/v1/compute", req(ts))
        r = out["results"]
        self.assertEqual([self._codes(r[i]) for i in (0, 1, 2, 3)],
                         [{"OUT_OF_RANGE"}, set(), {"OUT_OF_RANGE"}, {"OUT_OF_RANGE"}])

    def test_houses_undefined_polar(self):
        for lat in (80.0, -80.0, 67.0):
            _, out = self.api.post("/v1/compute", req([SYN_TIMES[3]], place=(lat, 10.0)))
            item = out["results"][0]
            self.assertEqual(self._codes(item), {"HOUSES_UNDEFINED"})
            self.assertTrue(all(b["ok"] for b in item["bodies"].values()))

    def test_ephe_file_missing(self):
        d = temp_ephe_copy()
        try:
            eng = Engine(d)
            os.remove(os.path.join(d, "sepl_18.se1"))
            out = eng.compute(req([SYN_TIMES[3]], bodies=["太阳"], place=(10.0, 20.0)))
            item = out["results"][0]
            self.assertEqual(self._codes(item), {"EPHE_FILE_MISSING"})
            self.assertTrue(item["houses"]["ok"])   # houses need no ephemeris file
        finally:
            shutil.rmtree(d, ignore_errors=True)
            swe.set_ephe_path(EPHE)

    def test_source_check_failed_when_forced_to_moshier(self):
        eng = Engine(EPHE, swe_module=ForcedMoshier())
        out = eng.compute(req([SYN_TIMES[3]], place=(10.0, 20.0)))
        item = out["results"][0]
        self.assertEqual(self._codes(item), {"SOURCE_CHECK_FAILED"})
        self.assertTrue(all(not b["ok"] for b in item["bodies"].values()))
        self.assertTrue(item["houses"]["ok"])

    def test_internal_is_per_body(self):
        eng = Engine(EPHE, swe_module=Exploding(swe.SATURN))
        out = eng.compute(req([SYN_TIMES[3], SYN_TIMES[4]], place=(10.0, 20.0)))
        for item in out["results"]:
            self.assertEqual(self._codes(item), {"INTERNAL"})
            self.assertEqual(item["bodies"]["土星"], {"ok": False, "error": "INTERNAL"})
            self.assertTrue(all(b["ok"] for n, b in item["bodies"].items() if n != "土星"))
        self.assertEqual(out["results"][0]["bodies"]["太阳"]["lon"].hex(),
                         swe.calc_ut(SYN_TIMES[3], swe.SUN, SW)[0][0].hex())


    def test_zz_all_six_codes_were_triggered(self):
        # unittest runs methods alphabetically, so this one runs last in the class
        self.assertEqual(self.seen, set(ERROR_CODES))


class Startup(unittest.TestCase):
    def test_refuses_on_sha_mismatch(self):
        d = temp_ephe_copy()
        try:
            p = os.path.join(d, "semo_18.se1")
            with open(p, "r+b") as f:
                f.seek(1000)
                b = f.read(1)
                f.seek(1000)
                f.write(bytes([b[0] ^ 1]))
            with self.assertRaises(EpheIntegrityError):
                Engine(d)
            r = subprocess.run([sys.executable, "-m", "ephemeris_service", "--port", "0", "--ephe-dir", d],
                               cwd=REPO, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 2)
            self.assertIn("refusing to start", r.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_refuses_when_file_missing(self):
        d = temp_ephe_copy()
        try:
            os.remove(os.path.join(d, "seas_18.se1"))
            with self.assertRaises(EpheIntegrityError):
                Engine(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Privacy(unittest.TestCase):
    def test_log_has_no_times_or_coordinates(self):
        eng = Engine(EPHE)
        buf = io.StringIO()
        with redirect_stderr(buf):
            run = Running(eng)
            try:
                run.post("/v1/compute", req([2451545.0, 2459580.25], place=(12.3456, 78.9012)))
                run.post("/v1/compute", req(["x"], place=(12.3456, 78.9012)))
                run.post("/v1/compute", None, raw="garbage")
                run.get("/health")
            finally:
                run.close()
        log = buf.getvalue()
        self.assertTrue(log.strip())
        for secret in ("2451545", "2459580", "12.3456", "78.9012", "x\""):
            self.assertNotIn(secret, log)
        for line in log.strip().splitlines():
            self.assertRegex(line, r"^(GET|POST) /\S* \d{3}$")

    def test_engine_keeps_no_request_state(self):
        eng = Engine(EPHE)
        before = dict(vars(eng))
        eng.compute(req([2451545.0], place=(12.3456, 78.9012)))
        self.assertEqual(set(vars(eng)), set(before))
        text = repr(vars(eng))
        self.assertNotIn("12.3456", text)


if __name__ == "__main__":
    unittest.main()
