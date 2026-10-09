import os
import re
import io
import pandas as pd
import matplotlib.pyplot as plt
import ixon, influxdb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Temporary testing debugging
from pathlib import Path
import plotting_dev as plot_

load_dotenv()  # reads .env into environment variables, if the file exists

API_TOKEN = os.environ["API_TOKEN"]
IXON_EMAIL = os.environ["IXON_EMAIL"]

# Debug
print(IXON_EMAIL)

def main():
    print("Running dts-fleet-overview main.py")

    # Hard-coded configs dictionary for now
    cfg = {
    "device": "Leak Detector 00 Cloud (InfluxDB)",
    "bucket": "",
    "serial": (),
    "system_label": "",
    "device_tokens": {
        "Leak Detector 00 Cloud": "o-3RNpNHd0h1d01jDoSTN93TqMKz-TWUqNzUSLb28WuwQTbOlybgs32Rn65zWUDrDWCK0Yx5sk016tlyupne-A=="
    },
    "output_folder": ""
    }


    # -- Authenticate Ixon login -- #

    ixon_headers, ixon_devices = ixon.authenticate()


    # -- Initialize session and check database contents -- #

    # Start a WebAccess proxy session
    session, proxy_base = ixon.start_session(ixon_headers, ixon_devices, cfg)

    # DTS buckets
    ## Each DTS has it's own bucket in InfluxDB

    # Get buckets
    print("  Fetching DTS buckets...")
    buckets = influxdb.list_buckets(session, proxy_base)
    if not buckets:
        print("Could not list buckets.")
        return
    all_buckets = sort_buckets_for_display(buckets)

    print(all_buckets)
    
    buckets = all_buckets[0:11] # Temporary testing fixed number of buckets
    number_of_timestamps = 5 # From each bucket

    
    # -- Fetch latest timestamps from each DTS bucket -- #
    results = {}
    for bucket in buckets:
        data_csv = fetch_last_traces(session, proxy_base, bucket, number_of_timestamps)

        if data_csv is None:
            print(f"Skipping bucket {bucket}")
            continue

        results[bucket] = data_csv
        Path(f"cache/{bucket}.csv").write_text(data_csv)   # one cache file per bucket

    # -- Plot results -- #
    

"""
    # Test debug
    # Save csv for faster testing
    CACHE = Path("cache/last_traces.csv")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(data_csv)

    plot_.main()
"""

def sort_buckets_for_display(buckets: list[str]) -> list[str]:
    """Show PLS buckets first in numeric order, then other buckets in fetched order."""
    pls_buckets = []
    other_buckets = []
    for i, name in enumerate(buckets):
        match = re.fullmatch(r"PLS[-_](\d+)", name, re.IGNORECASE)
        if match:
            pls_buckets.append((int(match.group(1)), i, name))
        else:
            other_buckets.append((i, name))

    ordered_pls = [name for _, _, name in sorted(pls_buckets, key=lambda x: (x[0], x[1]))]
    ordered_other = [name for _, name in other_buckets]
    return ordered_pls + ordered_other


def discover_influxdb_schema(session, proxy_base, bucket: str) -> tuple[str, str]:
    print(f"\n  Discovering schema for {bucket}...")
    measurements = influxdb.list_measurements(session, proxy_base, bucket, debug=True)
    fields = influxdb.list_field_keys(session, proxy_base, bucket, debug=True)

    # Testing debugging
    print("measurements")
    print(measurements)
    print("fields")
    print(fields)

    measurement = "Data"
    field = "Temperature"

    if not measurements:
        print(f"No measurements found in bucket '{bucket}'.")
        influxdb.diagnose_bucket(session, proxy_base, bucket)
        return "", ""
    elif "Data" not in measurements:
        print(f"Measurement 'Data' not found. Available: {measurements}")
        if len(measurements) == 1:
            measurement = measurements[0]
            print(f"Using measurement: {measurement}")
        else:
            print(f"Measurement: {measurement}")
    else:
        print(f"Measurement: {measurement}")

    if fields and "Temperature" not in fields:
        print(f"Field 'Temperature' not found. Available: {fields}")
        if len(fields) == 1:
            field = fields[0]
            print(f"Using field: {field}")
        else:
            print(f"Fields: {fields}")
    elif fields:
        print(f"Field: {field}")

    return measurement, field

def fetch_last_traces(session, proxy_base, bucket: str, n: int) -> str | None:

    # Get bucket schema
    measurement, field = discover_influxdb_schema(session, proxy_base, bucket)
    print(f"Measurement: {measurement}; field: {field}")

    # Check latest timestamp
    print(f"    Checking available data range...")
    total_time_range = influxdb.get_time_range(session, proxy_base, bucket, measurement, None)
    if total_time_range:
        print(f"Data available: {total_time_range[0]} -> {total_time_range[1]}")
    else:
        print("Could not determine data range. The bucket may be empty or the query timed out.")
        influxdb.diagnose_bucket(session, proxy_base, bucket)
        return None


    # -- Import DTS data as CSV -- #

    # Build query
    last_timestamp_str = total_time_range[1]
    last_timestamp = datetime.fromisoformat(last_timestamp_str)

    query = influxdb.build_last_n_query(
        bucket, measurement, field, last_timestamp, n)

    # Fetch data by running query
    print(f"    Fetching data from the {n} latest timestamps...")

    data_csv = influxdb.flux_query(session, proxy_base, query, debug=True)


    # -- Validate CSV -- #
    
    if data_csv:
        print(f"Fetched data")
    else:
        print("Failed to fetch latest data as CSV from InfluxDB query.")
        print("Debug info:")
        print(f'Bucket = {bucket}')
        print(f'Last timestamp = {last_timestamp}')
        print(f'Number of requested timestamps = {n}')
        print("Failed flux query:")
        print(query)
        return None

    if len(data_csv) >= 1000:
        print(data_csv[0:1000])

    check_data_rows = [l for l in data_csv.splitlines() if l.strip() and not l.startswith("#")]
    if not check_data_rows:
        print("Received CSV with no data from InfluxDB query")
        return None

    return data_csv

if __name__ == "__main__":
    main()