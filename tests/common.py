# -*- coding: utf-8 -*-
"""Shared helpers. All inputs in the tests are synthetic."""
import http.client
import json
import os
import shutil
import tempfile
import threading

import swisseph as swe

from ephemeris_service.core import BODIES, Engine
from ephemeris_service.server import make_server

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPHE = os.path.join(REPO, "ephe")

# synthetic instants and places
SYN_TIMES = [2378497.0, 2415020.5, 2440587.5, 2451545.0, 2459580.25, 2469807.123456789, 2597641.0]
SYN_PLACES = [(10.0, 20.0), (-33.5, 151.25), (55.75, -3.125), (0.0, 0.0), (66.0, 100.0)]
ALL_BODIES = list(BODIES)
FLAGS = ["SWIEPH", "SPEED"]


def temp_ephe_copy():
    d = tempfile.mkdtemp(prefix="ephe_copy_")
    for n in os.listdir(EPHE):
        if n.endswith(".se1"):
            shutil.copy(os.path.join(EPHE, n), d)
    return d


class Running:
    """A server on an ephemeral local port, plus a tiny HTTP client."""

    def __init__(self, engine):
        self.srv = make_server(engine, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.srv.server_address[1]
        self.conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)

    def post(self, path, obj, raw=None):
        body = raw if raw is not None else json.dumps(obj, allow_nan=False)
        self.conn.request("POST", path, body=body.encode("utf-8") if isinstance(body, str) else body,
                          headers={"Content-Type": "application/json"})
        r = self.conn.getresponse()
        data = r.read()
        return r.status, json.loads(data.decode("utf-8"))

    def get(self, path):
        self.conn.request("GET", path)
        r = self.conn.getresponse()
        data = r.read()
        return r.status, json.loads(data.decode("utf-8"))

    def close(self):
        self.conn.close()
        self.srv.shutdown()
        self.srv.server_close()


class ForcedMoshier:
    """pyswisseph stand-in that quietly drops the Swiss-ephemeris bit (as pyswisseph does when files are unusable)."""

    def __init__(self):
        self._real = swe

    def __getattr__(self, name):
        return getattr(self._real, name)

    def calc_ut(self, jd, ipl, flags):
        return swe.calc_ut(jd, ipl, (flags & ~swe.FLG_SWIEPH) | swe.FLG_MOSEPH)


class Exploding:
    """pyswisseph stand-in whose calc_ut raises for one chosen body."""

    def __init__(self, bad_ipl):
        self._real = swe
        self.bad_ipl = bad_ipl

    def __getattr__(self, name):
        return getattr(self._real, name)

    def calc_ut(self, jd, ipl, flags):
        if ipl == self.bad_ipl:
            raise RuntimeError("synthetic failure")
        return swe.calc_ut(jd, ipl, flags)
