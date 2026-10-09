# -*- coding: utf-8 -*-
"""python -m ephemeris_service [--host 127.0.0.1] [--port 8765] [--ephe-dir DIR]"""
import argparse
import os
import sys

from .core import Engine, EpheIntegrityError
from .server import make_server


def main(argv=None):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(prog="ephemeris_service")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--ephe-dir", default=os.path.join(here, "ephe"))
    a = ap.parse_args(argv)
    try:
        engine = Engine(a.ephe_dir)
    except EpheIntegrityError as exc:
        sys.stderr.write("refusing to start: ephemeris integrity check failed (%s)\n" % exc)
        return 2
    srv = make_server(engine, a.host, a.port)
    sys.stderr.write("listening on %s:%d\n" % srv.server_address[:2])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
