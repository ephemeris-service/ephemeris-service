# -*- coding: utf-8 -*-
"""A client that disconnects right after sending its request must leave no client address,
no traceback and no exception text in the log. All values below are synthetic."""
import io
import json
import re
import socket
import struct
import time
import unittest
from contextlib import redirect_stderr

from ephemeris_service.core import Engine
from tests.common import ALL_BODIES, EPHE, FLAGS, Running

LOG_LINE = re.compile(r"^((GET|POST|<method>) (/health|/version|/v1/compute|/v1/julday|/v1/revjul|<unknown>) \d{3}"
                      r"|connection error: \w+)$")


def abort_after_send(port, raw):
    """Send the request, then reset the connection without reading the reply."""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(raw)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))  # close sends RST
    s.close()


class DisconnectLeavesNoTrace(unittest.TestCase):
    def run_case(self, raw):
        eng = Engine(EPHE)
        buf = io.StringIO()
        with redirect_stderr(buf):
            run = Running(eng)
            try:
                for _ in range(20):
                    abort_after_send(run.port, raw)
                time.sleep(1.0)  # let the handler threads finish
            finally:
                run.close()
        log = buf.getvalue()
        self.assertNotIn("127.0.0.1", log)
        self.assertNotIn("Traceback", log)
        for line in log.splitlines():
            self.assertRegex(line, LOG_LINE)
        return log

    def test_post_compute(self):
        body = json.dumps({"times": [2451545.0 + 0.001 * i for i in range(400)], "bodies": ALL_BODIES,
                           "flags": FLAGS, "lat": 10.0, "lon": 20.0, "house_system": "P"}).encode("utf-8")
        raw = (b"POST /v1/compute HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
               b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        self.run_case(raw)

    def test_get_version(self):
        self.run_case(b"GET /version HTTP/1.1\r\nHost: x\r\n\r\n")


if __name__ == "__main__":
    unittest.main()
