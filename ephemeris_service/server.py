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
    (and any query string) is never logged, it appears as the fixed marker <unknown>,
    and a method other than GET and POST as <method>; the request line itself is
    never logged;
  * only GET and POST are served, any other method gets a fixed 405; a malformed
    request line or protocol version gets a fixed 400; every error reply carries
    fixed text only (status phrase and body), nothing taken from the request line.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import API_VERSION, RequestError

MAX_BODY_BYTES = 16 * 1024 * 1024

KNOWN_ROUTES = {("GET", "/health"), ("GET", "/version"),
                ("POST", "/v1/compute"), ("POST", "/v1/julday"), ("POST", "/v1/revjul")}
UNKNOWN_ROUTE = "<unknown>"
UNKNOWN_METHOD = "<method>"
ERROR_PHRASES = {400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed", 414: "URI Too Long",
                 431: "Request Header Fields Too Large", 500: "Internal Server Error"}
ERROR_BODY = b'{"error":"INVALID_INPUT"}'


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
            # The request line is never written. A line is: method (GET or POST only, else the
            # fixed marker), route (only a recognised fixed route, else a fixed marker), status code.
            method = self.command if self.command in ("GET", "POST") else UNKNOWN_METHOD
            path = getattr(self, "path", "").split("?", 1)[0]
            shown = path if (method, path) in KNOWN_ROUTES else UNKNOWN_ROUTE
            sys.stderr.write("%s %s %s\n" % (method, shown, code))

        def log_error(self, fmt, *args):
            pass

        # -- error replies: fixed text only, nothing from the request line --------------
        def send_error(self, code, message=None, explain=None):
            # Replaces the stdlib error page, whose status line and body quote the method,
            # the request version or the request line. `message` and `explain` are ignored.
            if code == 501:  # method other than GET / POST
                code = 405
            elif code not in ERROR_PHRASES:  # malformed request line, bad protocol version, ...
                code = 400
            body = ERROR_BODY
            self.log_request(code)
            self.close_connection = True
            head = ["HTTP/1.1 %d %s" % (code, ERROR_PHRASES[code]),
                    "Server: %s" % self.version_string(),
                    "Date: %s" % self.date_time_string(),
                    "Connection: close",
                    "Content-Type: application/json; charset=utf-8",
                    "Content-Length: %d" % len(body)]
            self.wfile.write(("\r\n".join(head) + "\r\n\r\n").encode("latin-1") + body)

        def parse_request(self):
            ok = super().parse_request()
            if ok and self.request_version not in ("HTTP/1.0", "HTTP/1.1"):  # incl. no version at all
                self.send_error(400)
                return False
            return ok

        # -- helpers -----------------------------------------------------------------
        def _send(self, status, obj):
            body = json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _take_body(self):
            """Consume the request body (by Content-Length) before any reply, on every route, so a
            kept-alive connection stays correctly framed. A body that cannot be framed (no or bad
            Content-Length, or larger than MAX_BODY_BYTES) is not read; the connection is closed
            after the reply instead."""
            self._raw = None
            if self.headers.get("Transfer-Encoding") is not None:
                self.close_connection = True
                return
            h = self.headers.get("Content-Length")
            if h is None:
                return
            try:
                n = int(h)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY_BYTES:
                self.close_connection = True
                return
            self._raw = self.rfile.read(n)

        def _read_json(self):
            if self._raw is None:
                raise RequestError("Content-Length required or body too large")
            try:
                return json.loads(self._raw.decode("utf-8"), parse_constant=_reject_constant)
            except (UnicodeDecodeError, ValueError):
                raise RequestError("body is not valid JSON")

        # -- routes ------------------------------------------------------------------
        def do_GET(self):
            self._take_body()
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._send(200, {"status": "ok"})
            elif path == "/version":
                self._send(200, engine.version_info())
            else:
                self._send(404, {"error": "NOT_FOUND"})

        def do_POST(self):
            self._take_body()
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
            except Exception as exc:  # only the exception type name is logged, the reply is a fixed code
                sys.stderr.write("internal error: %s\n" % type(exc).__name__)
                self._send(500, {"error": "INTERNAL"})

    return Handler


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # Replaces the stdlib report, which prints the client address and a traceback.
        # Only the exception type name is written; nothing else.
        exc = sys.exc_info()[1]
        sys.stderr.write("connection error: %s\n" % type(exc).__name__)


def make_server(engine, host="127.0.0.1", port=0):
    srv = _Server((host, port), make_handler(engine))
    srv.daemon_threads = True
    return srv
