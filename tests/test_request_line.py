# -*- coding: utf-8 -*-
"""Nothing from the request line (method, path, protocol version) may appear in the log or in any
error reply: status line, headers, body. All values below are synthetic."""
import io
import itertools
import socket
import unittest
from contextlib import redirect_stderr

from ephemeris_service.core import Engine
from tests.common import EPHE, Running

# numbers shaped like instants (JD) and like coordinates
VALUES = ["2451545.123", "39.9042", "2459580.25", "-33.5", "151.25", "12.3456", "78.9012", "2378497.0",
          "55.75", "2469807.123456789"]


def exchange(port, raw):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        s.sendall(raw)
        buf = b""
        try:
            while True:
                d = s.recv(65536)
                if not d:
                    break
                buf += d
        except socket.timeout:
            pass
    finally:
        s.close()
    head, _, body = buf.decode("latin-1").partition("\r\n\r\n")
    lines = head.split("\r\n")
    return lines[0], lines[1:], body


def request_lines(a, b):
    """Request lines with synthetic numbers placed in the method, path and version positions."""
    return [
        (a + " /health HTTP/1.1", 405),                       # method position
        (a + b + " /health HTTP/1.1", 405),
        ("GET" + a + " /health HTTP/1.1", 405),
        (a + " /v1/compute HTTP/1.1", 405),
        ("GET /%s/%s HTTP/1.1" % (a, b), 404),                # path position
        ("POST /x/%s?lat=%s&lon=%s HTTP/1.1" % (a, a, b), 404),
        ("GET /v1/compute?jd=%s HTTP/1.1" % a, 404),
        ("GET /health HTTP/%s" % a, 400),                     # protocol version position
        ("GET /health HTTP/%s.%s" % (a, b), 400),
        ("GET /health %s" % a, 400),
        ("GET /health HTTP/2.0", 400),
        ("GET %s" % a, 400),                                  # malformed request line
        ("GET /health %s %s HTTP/1.1" % (a, b), 400),
        ("%s %s %s %s" % (a, b, a, b), 400),
    ]


class RequestLineIsNeverEchoed(unittest.TestCase):
    def test_fuzz_values_in_method_path_and_version(self):
        eng = Engine(EPHE)
        buf = io.StringIO()
        seen = []
        with redirect_stderr(buf):
            run = Running(eng)
            try:
                for a, b in itertools.islice(itertools.permutations(VALUES, 2), 0, None, 7):
                    for line, status in request_lines(a, b):
                        raw = (line + "\r\nHost: x\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").encode("latin-1")
                        st, headers, body = exchange(run.port, raw)
                        seen.append((line, status, st, headers, body, a, b))
            finally:
                run.close()
        log = buf.getvalue()
        self.assertGreater(len(seen), 100)
        for line, want, st, headers, body, a, b in seen:
            self.assertTrue(st.startswith("HTTP/1.1 %d " % want), (want, st))
            for v in (a, b):
                for part in (st, "\n".join(headers), body):
                    self.assertNotIn(v, part, line)
            if want in (400, 405):
                self.assertEqual(body, '{"error":"INVALID_INPUT"}')
        for v in VALUES:
            self.assertNotIn(v, log)
        for l in log.strip().splitlines():
            self.assertRegex(l, r"^(GET|POST|<method>) (/health|/version|/v1/compute|/v1/julday|/v1/revjul|<unknown>) \d{3}$")

    def test_fixed_status_phrases_and_marker(self):
        eng = Engine(EPHE)
        buf = io.StringIO()
        with redirect_stderr(buf):
            run = Running(eng)
            try:
                for line, status, phrase in (("PUT /health HTTP/1.1", 405, "Method Not Allowed"),
                                             ("DELETE /v1/compute HTTP/1.1", 405, "Method Not Allowed"),
                                             ("GET /health HTTP/9.9", 400, "Bad Request"),
                                             ("GET /health", 400, "Bad Request")):
                    st, headers, body = exchange(run.port, (line + "\r\nHost: x\r\n\r\n").encode("latin-1"))
                    self.assertEqual(st, "HTTP/1.1 %d %s" % (status, phrase))
                    self.assertIn("Connection: close", headers)
            finally:
                run.close()
        self.assertEqual(buf.getvalue().strip().splitlines(),
                         ["<method> <unknown> 405", "<method> <unknown> 405", "<method> <unknown> 400",
                          "GET /health 400"])  # a recognised route, so it may be shown

    def test_valid_requests_unchanged(self):
        eng = Engine(EPHE)
        with redirect_stderr(io.StringIO()):
            run = Running(eng)
            try:
                st, headers, body = exchange(run.port, b"GET /health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                self.assertEqual(st, "HTTP/1.1 200 OK")
                self.assertEqual(body, '{"status":"ok"}')
                st, _, body = exchange(run.port, b"GET /nope HTTP/1.0\r\n\r\n")
                self.assertTrue(st.endswith(" 404 Not Found"), st)
            finally:
                run.close()


if __name__ == "__main__":
    unittest.main()
