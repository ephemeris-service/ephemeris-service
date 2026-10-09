# -*- coding: utf-8 -*-
"""Ephemeris computation core.

Given instants (JD_UT), a location and a list of bodies, return astronomical
numbers. Nothing else: no identity, no purpose, no persistence.

The core never logs or stores a request or its result.
"""

import hashlib
import math
import os
import threading

import swisseph as swe

API_VERSION = "1"
SERVICE_VERSION = "0.1.0"

# Closed sets -----------------------------------------------------------------

BODIES = {
    "太阳": swe.SUN,
    "月亮": swe.MOON,
    "水星": swe.MERCURY,
    "金星": swe.VENUS,
    "火星": swe.MARS,
    "木星": swe.JUPITER,
    "土星": swe.SATURN,
    "天王星": swe.URANUS,
    "海王星": swe.NEPTUNE,
    "冥王星": swe.PLUTO,
    "真北交": swe.TRUE_NODE,
}

FLAG_NAMES = ("SWIEPH", "SPEED")  # Swiss ephemeris, with speed

HOUSE_SYSTEMS = ("P",)  # Placidus. pyswisseph silently falls back to Placidus
#                         for unknown codes, so the set is closed here.

ERROR_CODES = (
    "INVALID_INPUT",
    "OUT_OF_RANGE",
    "EPHE_FILE_MISSING",
    "HOUSES_UNDEFINED",
    "SOURCE_CHECK_FAILED",
    "INTERNAL",
)

# Coverage of the three bundled files (seas_18, semo_18, sepl_18): 1800-01-01 to
# 2400-01-01. Conservative bounds, verified against pyswisseph 2.10.3.2 for all
# bodies in BODIES (see tests/test_coverage.py).
JD_MIN = 2378497.0
JD_MAX = 2597641.0

# sha256 of the bundled ephemeris files. The service refuses to start on any mismatch.
EPHE_SHA256 = {
    "seas_18.se1": "a2cd8fc33807c78ca9a700c91c2e042258b12fc4796519e00781440b5ad8b2e2",
    "semo_18.se1": "1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7",
    "sepl_18.se1": "ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66",
}
EPHE_BASIS = "JPL DE441"

MAX_TIMES = 200000
MAX_CALENDAR_YEAR = 9999
MIN_CALENDAR_YEAR = -4712

REQUEST_KEYS = {"times", "bodies", "flags", "lat", "lon", "house_system"}


class RequestError(ValueError):
    """The whole request is malformed (HTTP 400, code INVALID_INPUT)."""


class EpheIntegrityError(RuntimeError):
    """A bundled ephemeris file is missing or its sha256 differs."""


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_ephe_dir(ephe_dir):
    """Raise EpheIntegrityError unless every bundled file is present with the expected sha256."""
    bad = []
    for name, expected in EPHE_SHA256.items():
        path = os.path.join(ephe_dir, name)
        if not os.path.isfile(path):
            bad.append("%s: missing" % name)
        elif file_sha256(path) != expected:
            bad.append("%s: sha256 mismatch" % name)
    if bad:
        raise EpheIntegrityError("; ".join(bad))


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _finite(x):
    return _is_number(x) and math.isfinite(x)


def _all_finite(seq):
    return all(math.isfinite(v) for v in seq)


class Engine:
    """Stateless apart from the (process-global) Swiss Ephemeris path.

    Swiss Ephemeris keeps global state and is not thread safe, so every call
    into it is serialised by one lock.
    """

    def __init__(self, ephe_dir, swe_module=None, verify=True):
        self.ephe_dir = os.path.abspath(ephe_dir)
        self.swe = swe_module if swe_module is not None else swe
        if verify:
            verify_ephe_dir(self.ephe_dir)
        self._lock = threading.Lock()
        self._flags_speed = swe.FLG_SWIEPH | swe.FLG_SPEED
        self._flags_nospeed = swe.FLG_SWIEPH
        self._info = {
            "swisseph_version": swe.version,
            "basis": EPHE_BASIS,
            "files": dict(EPHE_SHA256),
        }

    # -- info ------------------------------------------------------------------
    def version_info(self):
        return {
            "service_version": SERVICE_VERSION,
            "api_version": API_VERSION,
            "ephemeris": self._info,
            "jd_ut_range": [JD_MIN, JD_MAX],
            "error_codes": list(ERROR_CODES),
        }

    # -- request validation -------------------------------------------------------
    def _parse_request(self, req):
        if not isinstance(req, dict):
            raise RequestError("request must be an object")
        extra = set(req) - REQUEST_KEYS
        if extra:
            raise RequestError("unknown field(s)")
        times = req.get("times")
        if not isinstance(times, list) or len(times) > MAX_TIMES:
            raise RequestError("times must be a list (max %d)" % MAX_TIMES)
        bodies = req.get("bodies")
        if (not isinstance(bodies, list) or not bodies
                or not all(isinstance(b, str) and b in BODIES for b in bodies)
                or len(set(bodies)) != len(bodies)):
            raise RequestError("bodies must be a non-empty list of distinct names from the closed set")
        flags = req.get("flags")
        if (not isinstance(flags, list) or not all(isinstance(f, str) and f in FLAG_NAMES for f in flags)
                or "SWIEPH" not in flags or len(set(flags)) != len(flags)):
            raise RequestError("flags must be a subset of the closed set and contain SWIEPH")
        loc_keys = [k for k in ("lat", "lon", "house_system") if k in req]
        if loc_keys and len(loc_keys) != 3:
            raise RequestError("lat, lon and house_system go together")
        return times, bodies, ("SPEED" in flags), bool(loc_keys)

    def _houses_input_error(self, req):
        """None if the location input is valid, else True (every houses entry becomes INVALID_INPUT)."""
        lat, lon, hs = req["lat"], req["lon"], req["house_system"]
        if not (_finite(lat) and _finite(lon)):
            return True
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return True
        if not isinstance(hs, str) or hs not in HOUSE_SYSTEMS:
            return True
        return False

    # -- compute -----------------------------------------------------------------
    def compute(self, req):
        times, bodies, want_speed, want_houses = self._parse_request(req)
        houses_bad = self._houses_input_error(req) if want_houses else False
        lat = float(req["lat"]) if want_houses and not houses_bad else None
        lon = float(req["lon"]) if want_houses and not houses_bad else None
        flags = self._flags_speed if want_speed else self._flags_nospeed

        results = []
        with self._lock:
            self.swe.set_ephe_path(self.ephe_dir)
            files_ok = all(os.path.isfile(os.path.join(self.ephe_dir, n)) for n in EPHE_SHA256)
            for t in times:
                results.append(self._one_time(t, bodies, flags, want_speed, files_ok,
                                              want_houses, houses_bad, lat, lon))
        return {"api_version": API_VERSION, "ephemeris": self._info, "results": results}

    def _one_time(self, t, bodies, flags, want_speed, files_ok, want_houses, houses_bad, lat, lon):
        if not _finite(t):
            return {"jd_ut": None, "error": "INVALID_INPUT"}
        jd = float(t)
        if jd < JD_MIN or jd > JD_MAX:
            return {"jd_ut": jd, "error": "OUT_OF_RANGE"}
        item = {"jd_ut": jd, "error": None, "bodies": {}}
        for name in bodies:
            item["bodies"][name] = self._one_body(jd, BODIES[name], flags, want_speed, files_ok)
        if want_houses:
            item["houses"] = self._houses(jd, houses_bad, lat, lon)
        return item

    def _one_body(self, jd, ipl, flags, want_speed, files_ok):
        if not files_ok:
            return {"ok": False, "error": "EPHE_FILE_MISSING"}
        try:
            xx, retflag = self.swe.calc_ut(jd, ipl, flags)
        except Exception:
            return {"ok": False, "error": "INTERNAL"}
        if not (retflag & swe.FLG_SWIEPH):
            return {"ok": False, "error": "SOURCE_CHECK_FAILED"}
        if len(xx) < 6 or not _all_finite(xx):
            return {"ok": False, "error": "INTERNAL"}
        out = {"ok": True, "lon": xx[0], "lat": xx[1], "dist": xx[2], "retflag": retflag}
        if want_speed:
            out.update({"lon_speed": xx[3], "lat_speed": xx[4], "dist_speed": xx[5]})
        return out

    def _houses(self, jd, houses_bad, lat, lon):
        if houses_bad:
            return {"ok": False, "error": "INVALID_INPUT"}
        try:
            cusps, ascmc = self.swe.houses(jd, lat, lon, b"P")
        except Exception as exc:
            # pyswisseph raises swisseph.Error for Placidus outside the polar limit
            if type(exc).__name__ == "Error":
                return {"ok": False, "error": "HOUSES_UNDEFINED"}
            return {"ok": False, "error": "INTERNAL"}
        cusps = list(cusps)
        if len(cusps) != 12 or len(ascmc) < 2 or not _all_finite(cusps) or not _all_finite(ascmc[:2]):
            return {"ok": False, "error": "INTERNAL"}
        return {"ok": True, "cusps": cusps, "asc": ascmc[0], "mc": ascmc[1]}

    # -- time conversion only ----------------------------------------------------------
    def julday(self, req):
        if not isinstance(req, dict) or set(req) - {"year", "month", "day", "hour", "calendar"}:
            raise RequestError("bad julday request")
        year, month, day, hour = (req.get(k) for k in ("year", "month", "day", "hour"))
        cal = req.get("calendar", "gregorian")
        if cal not in ("gregorian", "julian"):
            raise RequestError("bad calendar")
        for v in (year, month, day):
            if not isinstance(v, int) or isinstance(v, bool):
                raise RequestError("year, month, day must be integers")
        if not _finite(hour):
            raise RequestError("hour must be a finite number")
        if not (MIN_CALENDAR_YEAR <= year <= MAX_CALENDAR_YEAR and 1 <= month <= 12 and 1 <= day <= 31):
            raise RequestError("date out of range")
        with self._lock:
            jd = self.swe.julday(year, month, day, float(hour), 1 if cal == "gregorian" else 0)
        return {"jd_ut": jd}

    def revjul(self, req):
        if not isinstance(req, dict) or set(req) - {"jd_ut", "calendar"}:
            raise RequestError("bad revjul request")
        jd = req.get("jd_ut")
        cal = req.get("calendar", "gregorian")
        if not _finite(jd) or cal not in ("gregorian", "julian"):
            raise RequestError("bad revjul request")
        with self._lock:
            y, m, d, h = self.swe.revjul(float(jd), 1 if cal == "gregorian" else 0)
        return {"year": y, "month": m, "day": d, "hour": h}
