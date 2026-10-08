"""InfluxDB query helpers: schema discovery, Flux queries, diagnostics.

How this module fits together:
  - flux_query() is the only function that actually talks to InfluxDB with a
    Flux query. Everything else either builds a query string and passes it to
    flux_query(), or parses the CSV text that comes back.
  - The "schema discovery" functions ask InfluxDB *what exists* (bucket names,
    measurement names, field names, tag names, serial numbers, time range).
    They return small lists of names, not sensor data.
  - build_chunk_query() builds the query for the *actual data* (e.g. temperature
    readings) for one time window. The caller runs it through flux_query().

All requests go through `proxy_base`, a URL that tunnels to the InfluxDB
instance (via IXON), using an already-authenticated requests.Session.
"""

import requests
from datetime import datetime, timedelta, timezone

# InfluxDB organisation ID. Required by the /api/v2/query endpoint.
ORG_ID = "31b1bdd5d5103ead"


def flux_query(session: requests.Session, proxy_base: str, query: str,
               debug: bool = False, annotated: bool = False) -> str | None:
    """Run a Flux query. Returns raw CSV text, or None on error/timeout.

    If annotated=True, uses JSON body with dialect to include #group/#datatype/#default
    annotations and comma delimiters (matching InfluxDB Data Explorer export format).
    """
    # Start from the session's headers (which carry the auth token) and ask
    # InfluxDB to answer in CSV.
    headers = dict(session.headers)
    headers["Accept"] = "application/csv"

    # InfluxDB accepts a query in two ways:
    #   - annotated: a JSON body that also says how the CSV should look
    #     (adds the "#group/#datatype/#default" lines at the top).
    #   - plain: the raw Flux text as the request body.
    if annotated:
        headers["Content-Type"] = "application/json"
        body = {
            "query": query,
            "dialect": {
                "header": True,
                "delimiter": ",",
                "annotations": ["group", "datatype", "default"],
            },
        }
        post_kwargs = {"json": body}
    else:
        headers["Content-Type"] = "application/vnd.flux"
        post_kwargs = {"data": query}

    # This is the network call: send the query, wait up to 60s for the result.
    try:
        resp = session.post(
            f"{proxy_base}/api/v2/query?orgID={ORG_ID}",
            headers=headers,
            timeout=60,
            **post_kwargs,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        if debug:
            print(f"Connection error: {e}")
        return None
    if debug:
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
    # Success -> the CSV as one big string. Anything else -> None.
    return resp.text if resp.status_code == 200 else None


def _parse_csv_values(raw_csv: str) -> list[str]:
    """Extract _value column from Flux CSV output.

    Flux CSV format:
      #group,false,false,false     <- annotation (starts with #)
      ,result,table,_value         <- header row
      ,_result,0,Data              <- data row (empty first col)

    Used by the schema functions, whose results are just a list of names in
    the last column. Returns them de-duplicated and sorted.
    """
    values = []
    for line in raw_csv.splitlines():
        # Skip annotation lines and blank lines.
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split(",")
        if len(parts) >= 4:
            val = parts[-1].strip()
            # Skip the header row (whose last column is literally "_value").
            if val and val != "_value":
                values.append(val)
    return sorted(set(values))


# ── Schema discovery ─────────────────────────────────────────────────────────
# These functions answer "what's in the database?" They return names, not data.
# InfluxDB terms:
#   bucket      ~ a database
#   measurement ~ a table (e.g. "Data")
#   field       ~ a value column that holds readings (e.g. "Temperature")
#   tag         ~ an indexed label column used for filtering (e.g. "Serial number")

def list_buckets(session: requests.Session, proxy_base: str) -> list[str]:
    """Return the names of all user-created buckets (skips InfluxDB's system buckets)."""
    # Uses the REST API (JSON), not a Flux query.
    resp = session.get(f"{proxy_base}/api/v2/buckets?limit=100", timeout=15)
    if resp.status_code != 200:
        return []
    return [b["name"] for b in resp.json().get("buckets", []) if b.get("type") == "user"]


def list_measurements(session: requests.Session, proxy_base: str, bucket: str,
                      debug: bool = False) -> list[str]:
    """Return the measurement names in a bucket, e.g. ["Data"]."""
    query = f'import "influxdata/influxdb/schema"\nschema.measurements(bucket: "{bucket}")'
    raw = flux_query(session, proxy_base, query, debug=debug)
    return _parse_csv_values(raw) if raw else []


def list_field_keys(session: requests.Session, proxy_base: str, bucket: str,
                    debug: bool = False) -> list[str]:
    """Return the field names in a bucket, e.g. ["Temperature", ...]."""
    query = f'import "influxdata/influxdb/schema"\nschema.fieldKeys(bucket: "{bucket}")'
    raw = flux_query(session, proxy_base, query, debug=debug)
    return _parse_csv_values(raw) if raw else []


def list_tag_keys(session: requests.Session, proxy_base: str,
                  bucket: str, measurement: str) -> list[str]:
    """Return the tag names on a measurement, e.g. ["Meter", "Serial number"]."""
    query = (
        'import "influxdata/influxdb/schema"\n'
        f'schema.measurementTagKeys(bucket: "{bucket}", measurement: "{measurement}")'
    )
    raw = flux_query(session, proxy_base, query)
    if not raw:
        return []
    # Drop InfluxDB's built-in columns (_measurement, _field, ...).
    return [t for t in _parse_csv_values(raw) if not t.startswith("_")]


def list_serial_numbers(session: requests.Session, proxy_base: str,
                        bucket: str, measurement: str) -> list[str] | None:
    """Returns list of serial numbers, or None if the tag doesn't exist."""
    # Some buckets hold data for several devices, told apart by the
    # "Serial number" tag. If there's no such tag, the bucket is one device.
    tags = list_tag_keys(session, proxy_base, bucket, measurement)
    if "Serial number" not in tags:
        return None
    # Ask for every distinct value of the "Serial number" tag.
    query = (
        'import "influxdata/influxdb/schema"\n'
        f'schema.measurementTagValues(bucket: "{bucket}", '
        f'measurement: "{measurement}", tag: "Serial number")'
    )
    raw = flux_query(session, proxy_base, query)
    if not raw:
        return None
    values = _parse_csv_values(raw)
    return values if values else None


def get_time_range(session: requests.Session, proxy_base: str,
                   bucket: str, measurement: str,
                   serial: str | None) -> tuple[str, str] | None:
    """Checks last 10 years and returns (earliest_timestamp, latest_timestamp) or None."""
    # Optional extra filter line, only when we're looking at one device.
    serial_filter = (
        f'  |> filter(fn: (r) => r["Serial number"] == "{serial}")\n'
        if serial else ""
    )
    # Flux is a pipeline: each "|>" passes the rows on to the next step.
    # Here: all rows from the last 10 years for this measurement (and serial),
    # merged into a single table with group() so first()/last() see everything.
    base_query = (
        f'from(bucket: "{bucket}")\n'
        f'  |> range(start: -10y)\n'
        f'  |> filter(fn: (r) => r["_measurement"] == "{measurement}")\n'
        f'{serial_filter}'
        f'  |> group()\n'
    )
    # Two queries: one for the oldest row, one for the newest. Keep only the
    # timestamp column so the response is tiny.
    first_raw = flux_query(session, proxy_base,
                           base_query + '  |> first()\n  |> keep(columns: ["_time"])')
    last_raw = flux_query(session, proxy_base,
                          base_query + '  |> last()\n  |> keep(columns: ["_time"])')

    def extract_time(csv_text: str) -> str | None:
        # Find the first value that looks like an RFC3339 timestamp,
        # e.g. "2025-03-01T12:00:00Z".
        for line in csv_text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            for p in line.split(","):
                p = p.strip()
                if "T" in p and p.endswith("Z"):
                    return p
        return None

    if first_raw and last_raw:
        t1, t2 = extract_time(first_raw), extract_time(last_raw)
        if t1 and t2:
            return (t1, t2)
    return None


def diagnose_bucket(session: requests.Session, proxy_base: str, bucket: str):
    """Print diagnostic info when a bucket seems empty."""
    print("Bucket diagnostics")
    print(f"  Inspecting schema for bucket '{bucket}'...\n")

    measurements = list_measurements(session, proxy_base, bucket)
    fields = list_field_keys(session, proxy_base, bucket)

    print(f"  Measurements: {measurements or '(none found)'}")
    print(f"  Fields:       {fields or '(none found)'}")

    if measurements:
        for m in measurements:
            tags = list_tag_keys(session, proxy_base, bucket, m)
            print(f"  Tags in '{m}': {tags or '(none)'}")

    # Point out where the schema differs from what the downloader expects
    # (measurement "Data" with a "Temperature" field).
    if not measurements:
        print("Bucket has no measurements — it may be empty or use a different schema.")
    elif "Data" not in measurements:
        print(f"Expected measurement 'Data' but found: {measurements}")
    if fields and "Temperature" not in fields:
        print(f"Expected field 'Temperature' but found: {fields}")
    print()


# ── Data query ───────────────────────────────────────────────────────────────
# This is where the actual readings come from. build_chunk_query() only builds
# the query text; the caller passes it to flux_query() to fetch the data.
# The download is split into time windows ("chunks") so that no single request
# is too large or hits the 60s timeout.

def build_chunk_query(bucket: str, measurement: str, field: str,
                      serial: str | None,
                      start: datetime, stop: datetime) -> str:
    """Build a Flux query for one time window."""
    # InfluxDB wants timestamps in RFC3339 format (UTC, ending in "Z").
    start_rfc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    stop_rfc = stop.strftime("%Y-%m-%dT%H:%M:%SZ")
    serial_filter = (
        f'  |> filter(fn: (r) => r["Serial number"] == "{serial}")\n'
        if serial else ""
    )
    # Columns to remove from the output: they're the same on every row
    # (we already filtered on them), so they'd only bloat the CSV.
    drop_cols = '["_result","_start","_stop","_field","_measurement"'
    if serial:
        drop_cols += ',"Serial number"'
    drop_cols += ']'
    # The pipeline, step by step:
    #   1. from/range:  rows in this bucket within [start, stop)
    #   2. filter:      only this measurement and this field (e.g. Temperature)
    #   3. filter:      only this serial number (if given)
    #   4. filter:      skip rows whose "Meter" tag contains "-" (not a valid
    #                   number, e.g. negative or placeholder positions)
    #   5. drop:        remove the redundant columns listed above
    #   6. map:         turn "Meter" from text into a number so it sorts numerically
    #   7. sort:        by time (newest first), then re-sort by Meter (position
    #                   along the cable), so the final order is by Meter
    return (
        'import "strings"\n'
        f'from(bucket: "{bucket}")\n'
        f'  |> range(start: {start_rfc}, stop: {stop_rfc})\n'
        f'  |> filter(fn: (r) => r["_measurement"] == "{measurement}")\n'
        f'  |> filter(fn: (r) => r["_field"] == "{field}")\n'
        f'{serial_filter}'
        '  |> filter(fn: (r) => not strings.containsAny(v: r["Meter"], chars: "-"))\n'
        f'  |> drop(columns: {drop_cols})\n'
        '  |> map(fn: (r) => ({r with Meter: float(v: r.Meter)}))\n'
        '  |> sort(columns: ["_time"], desc: true)\n'
        '  |> sort(columns: ["Meter"], desc: false)'
    )

def build_last_n_query(bucket: str, measurement: str, field: str,
                      end: datetime, number: int) -> str:
    """Build a Flux query for a given number of timestamps."""

    # Create a search window leading up to the input end datetime
    start = end - timedelta(minutes=30)
    
    # InfluxDB wants timestamps in RFC3339 format (UTC, ending in "Z").
    start_rfc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_rfc = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    # First part of the flux query gets all data in the search window
    query_part_search_window = (
        'import "strings"\n'
        f'data = from(bucket: "{bucket}")\n'
        f'  |> range(start: {start_rfc}, stop: {end_rfc})\n'
        f'  |> filter(fn: (r) => r["_measurement"] == "{measurement}")\n'
        f'  |> filter(fn: (r) => r["_field"] == "{field}")\n'
        '  |> filter(fn: (r) => not strings.containsAny(v: r["Meter"], chars: "-"))\n'
        '  |> drop(columns: ["_result","_start","_stop","_field","_measurement","Serial number"])\n'
        '  |> map(fn: (r) => ({r with Meter: float(v: r.Meter)}))\n'
    )

    # Second part extracts the last {number} of timestamps
    query_part_extract_n_timestamps = (
        'times = data\n'
        '  |> group()\n'
        '  |> unique(column: "_time")\n'
        '  |> sort(columns: ["_time"], desc: true)\n'
#        '  |> sort(columns: ["Meter"], desc: false)\n'
        f'  |> limit(n:{number})\n'
        '  |> findColumn(fn: (key) => true, column: "_time")\n'
    )

    # Third part outputs the full data where _time matches the extracted timestamps
    query_part_output = (
        'data\n'
        '  |> filter(fn: (r) => contains(value: r._time, set: times))\n'
        '  |> group()\n'
        '  |> sort(columns: ["_time", "Meter"])\n'
    )

    return query_part_search_window + query_part_extract_n_timestamps + query_part_output