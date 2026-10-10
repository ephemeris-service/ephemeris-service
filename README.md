# ephemeris-service

A small local HTTP service that returns astronomical numbers from the Swiss Ephemeris:
given instants (JD_UT), a place and a list of bodies, it returns longitudes, latitudes, distances,
their speeds, and the twelve house cusps with ASC and MC. It knows no domain concepts: it does not
accept, log or store identifiers, purposes or thresholds, and it persists nothing.

Licence: GNU AGPL v3 (`LICENSE`). Swiss Ephemeris licence notice: `ephe/README.md`.
Runtime dependency: `pyswisseph==2.10.3.2` only. Python 3.11. Server: standard library `http.server`.

## Run

The service runs in its own virtual environment inside this repository (`.venv/`, not committed), with
`pyswisseph` as the only package installed:

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt          # pins pyswisseph==2.10.3.2; Windows: .venv\Scripts\python
    .venv/bin/python -m ephemeris_service --port 8765            # binds 127.0.0.1 by default

Callers that start the service for someone else (test fixtures, launch scripts) should use this
interpreter (`.venv/bin/python`, on Windows `.venv\Scripts\python.exe`), not their own.

The service checks the sha256 of the three files in `ephe/` at start-up and refuses to start
(exit status 2) if any is missing or differs. Keep the directory path ASCII-only: with a non-ASCII path
Swiss Ephemeris cannot open the files and quietly falls back to its built-in Moshier mode, which this
service reports as `SOURCE_CHECK_FAILED` for every body (it never returns such numbers).

## API (version 1)

`GET /health` -> `{"status":"ok"}` · `GET /version` -> versions, ephemeris file hashes, JD range, error codes.

`POST /v1/compute`

    {"times":[2451545.0, ...],              // JD_UT, doubles
     "bodies":["太阳","月亮","水星","金星","火星","木星","土星","天王星","海王星","冥王星","真北交"],
     "flags":["SWIEPH","SPEED"],            // closed set; SWIEPH required, SPEED optional
     "lat":10.0, "lon":20.0,                // degrees, north/east positive (optional, together with house_system)
     "house_system":"P"}                    // Placidus

Response (order follows the request): per instant, per body `lon lat dist lon_speed lat_speed dist_speed retflag`;
per instant `houses.cusps` (12), `asc`, `mc`; top-level `ephemeris` (Swiss Ephemeris version, file hashes).
Floats are serialised with their shortest exact representation (`repr`), so they round-trip bit for bit.
Errors are per item: `{"ok":false,"error":CODE}` or, for a whole instant, `"error":CODE`; one failing item
never affects the others. Closed set of codes:

| code | meaning |
|---|---|
| `INVALID_INPUT` | the item's input is not valid (a malformed whole request answers HTTP 400 with this code) |
| `OUT_OF_RANGE` | instant outside the bundled files' coverage (JD 2378497.0 – 2597641.0) |
| `EPHE_FILE_MISSING` | a bundled ephemeris file is missing at request time |
| `HOUSES_UNDEFINED` | Placidus is undefined at this latitude (polar circle) |
| `SOURCE_CHECK_FAILED` | the returned flags do not include the Swiss ephemeris (silent fallback detected) |
| `INTERNAL` | any other failure |

`POST /v1/julday` `{"year","month","day","hour","calendar"?}` and `POST /v1/revjul` `{"jd_ut","calendar"?}` convert
between calendar dates and JD only.

## Privacy

Request bodies and results are never stored. The access log holds method, route and status only (a path that is not one of the
fixed routes is logged as `<unknown>`): no body, no instants, no coordinates, no client address. Unknown request fields are rejected.

## Test

    python -m unittest discover -s . -t .
    python tools/bench.py            # batch latency against a resident service
    python tools/prerelease_scan.py --terms FILE --history   # pre-release scan; the term list is supplied by the releaser

## Source offer

The service is network software under AGPL-3.0: whoever runs a modified copy for others must offer them the
corresponding source, including the build and run material in this repository.
