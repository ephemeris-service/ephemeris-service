# -*- coding: utf-8 -*-
"""Local HTTP service (standard library only) around the ephemeris core.

Endpoints
  GET  /health         liveness, read-only
  GET  /version        service/api/ephemeris versions, read-only
  POST /v1/compute     bodies, houses for a list of JD_UT instants
  POST /v1/julday      calendar date -> JD   (time conversion only)
  POST /v1/revjul      JD -> calendar date   (time conversion only)

Privacy rules (nothing here knows why a number is asked for):
  * request bodies and results are never stored;
  * the access log records method, route and status only: no body, no times,
    no coordinates, no client address; a path that is not one of the routes above
    (and any query string) is never logged, it appears as the fixed marker <unknown>.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import API_VERSION, RequestError

MAX_BODY_BYTES = 16 * 1024 * 1024

KNOWN_ROUTES = {("GET", "/health"), ("GET", "/version"),
                ("POST", "/v1/compute"), ("POST", "/v1/julday"), ("POST", "/v1/revjul")}
UNKNOWN_ROUTE = "<unknown>"


def _reject_constant(name):
    raise ValueError("non-finite JSON constant")


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ephemeris-service/" + API_VERSION
        sys_version = ""

        # -- logging: method, path, status only ------------------------------------
        def log_message(self, fmt, *args):  # noqa: D401
            pass

        def log_request(self, code="-", size="-"):
            # Only a recognised fixed route is written; any other path (it may carry
            # arbitrary client text) is replaced by a fixed marker.
            path = getattr(self, "path", "").split("?", 1)[0]
            shown = path if (self.command, path) in KNOWN_ROUTES else UNKNOWN_ROUTE
            sys.stderr.write("%s %s %s\n" % (self.command, shown, code))

        def log_error(self, fmt, *args):
            pass

        # -- helpers -----------------------------------------------------------------
        def _send(self, status, obj):
            body = json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise RequestError("Content-Length required")
            if n < 0 or n > MAX_BODY_BYTES:
                raise RequestError("body too large")
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
            except (UnicodeDecodeError, ValueError):
                raise RequestError("body is not valid JSON")

        # -- routes ------------------------------------------------------------------
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._send(200, {"status": "ok"})
            elif path == "/version":
                self._send(200, engine.version_info())
            else:
                self._send(404, {"error": "NOT_FOUND"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            routes = {"/v1/compute": engine.compute, "/v1/julday": engine.julday, "/v1/revjul": engine.revjul}
            fn = routes.get(path)
            if fn is None:
                self._send(404, {"error": "NOT_FOUND"})
                return
            try:
                self._send(200, fn(self._read_json()))
            except RequestError:
                self._send(400, {"error": "INVALID_INPUT"})
            except Exception as exc:  # never echo request content
                sys.stderr.write("internal error: %s\n" % type(exc).__name__)
                self._send(500, {"error": "INTERNAL"})

    return Handler


def make_server(engine, host="127.0.0.1", port=0):
    srv = ThreadingHTTPServer((host, port), make_handler(engine))
    srv.daemon_threads = True
    return srv
