# -*- coding: utf-8 -*-
"""Batch latency against a resident service (synthetic instants only).

Starts the service as a separate process, sends N instants x 10 bodies + houses in one request,
repeats, and compares with calling pyswisseph directly in this process.
Usage: python tools/bench.py [--times 1000] [--reps 7]
"""
import argparse
import http.client
import json
import os
import socket
import statistics
import subprocess
import sys
import time

import swisseph as swe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODIES10 = ["太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"]
IPL10 = [swe.SUN, swe.MOON, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN, swe.URANUS,
         swe.NEPTUNE, swe.PLUTO]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def ms(t0):
    return (time.perf_counter() - t0) * 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--times", type=int, default=1000)
    ap.add_argument("--reps", type=int, default=7)
    a = ap.parse_args()
    times = [2451545.0 + i * 0.5 for i in range(a.times)]
    lat, lon = 10.0, 20.0
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ephemeris_service", "--port", str(port)], cwd=ROOT,
                            stderr=subprocess.DEVNULL)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        for _ in range(100):
            try:
                conn.request("GET", "/health")
                conn.getresponse().read()
                break
            except OSError:
                time.sleep(0.1)
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)

        def call(ts):
            body = json.dumps({"times": ts, "bodies": BODIES10, "flags": ["SWIEPH", "SPEED"],
                               "lat": lat, "lon": lon, "house_system": "P"}).encode()
            t0 = time.perf_counter()
            conn.request("POST", "/v1/compute", body=body, headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            data = r.read()
            dt = ms(t0)
            assert r.status == 200
            return dt, len(data), json.loads(data)

        call(times[:10])  # warm up
        single = [call(times[:1])[0] for _ in range(20)]
        batch, size = [], 0
        for _ in range(a.reps):
            dt, size, out = call(times)
            batch.append(dt)
        assert all(it["error"] is None for it in out["results"])

        swe.set_ephe_path(os.path.join(ROOT, "ephe"))
        F = swe.FLG_SWIEPH | swe.FLG_SPEED
        direct = []
        for _ in range(a.reps):
            t0 = time.perf_counter()
            for jd in times:
                for ipl in IPL10:
                    swe.calc_ut(jd, ipl, F)
                swe.houses(jd, lat, lon, b"P")
            direct.append(ms(t0))
        res = {
            "instants": a.times, "bodies": 10, "houses": True, "reps": a.reps,
            "service_batch_ms": {"min": round(min(batch), 1), "median": round(statistics.median(batch), 1),
                                 "max": round(max(batch), 1)},
            "direct_pyswisseph_ms": {"min": round(min(direct), 1), "median": round(statistics.median(direct), 1),
                                     "max": round(max(direct), 1)},
            "single_instant_request_ms": {"median": round(statistics.median(single), 2),
                                          "max": round(max(single), 2)},
            "response_bytes": size,
            "python": sys.version.split()[0], "pyswisseph": swe.version,
        }
        print(json.dumps(res, ensure_ascii=False, indent=1))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    main()
