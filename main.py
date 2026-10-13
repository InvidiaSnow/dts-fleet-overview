import os
import re
import io
import pandas as pd
import matplotlib.pyplot as plt
import ixon, influxdb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# Temporary testing debugging
from pathlib import Path
import plotting_dev as plot_

load_dotenv()  # reads .env into environment variables, if the file exists

API_TOKEN = os.environ["API_TOKEN"]
IXON_EMAIL = os.environ["IXON_EMAIL"]
NUMBER_OF_TIMESTAMPS = 3 # Number to get from each system

def main():
    print("Running dts-fleet-overview main.py")

    # Hard-coded configs dictionary for now
    cfg = {
    "device": "Leak Detector 00 Cloud (InfluxDB)",
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
    all_buckets, dts_systems = sort_buckets_for_display(buckets)
    
    buckets = all_buckets[0:11] # Temporary testing fixed number of buckets
    print(buckets)
    
    # -- Fetch latest timestamps from each DTS bucket -- #

    results = {}

    # Using parallel queries with a thread pool from the standard library
    # Output will still be in the correct order
    with ThreadPoolExecutor(max_workers=4) as pool:
        data_csvs = pool.map(lambda bucket: fetch_last_traces(session, proxy_base, bucket, NUMBER_OF_TIMESTAMPS), buckets)

    # Using dts_systems alongside buckets here because the bucket names are not ideal
    for bucket, dts_system, data_csv in zip(buckets, dts_systems, data_csvs): # zip pairs dts_system 1 to csv 1

        if data_csv is None:
            print(f"Skipping bucket {bucket} with data from DTS system {dts_system}")
            continue

        # Use names as DTS-systems, which is more correct than "PLS"
        # Building a dict with name-data pairs
        results[dts_system] = data_csv
        file_name = dts_system
        Path(f"cache/{file_name}.csv").write_text(data_csv)   # one cache file per bucket

    # -- Analyze results -- #

    # Currently being performed in plotting_dev.py
    # Planning to migrate this back here

    # -- Plot results -- #

    plot_.plot_overview(results)

"""
    # Test debug
    # Save csv for faster testing
    CACHE = Path("cache/last_traces.csv")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(data_csv)

    plot_.main()
"""

def sort_buckets_for_display(buckets: list[str]) -> tuple[list[str], list[str]]:
    """Sort PLS buckets first in numeric order, then other buckets in fetched order."""
    pls_buckets = []
    dts_systems = []
    other_buckets = []
    for i, bucket_name in enumerate(buckets):
        match = re.fullmatch(r"PLS[-_](\d+)", bucket_name, re.IGNORECASE)
        if match:
            pls_bucket_number_str = match.group(1)
            pls_buckets.append(( int(pls_bucket_number_str) , i, bucket_name ))

            if int(pls_bucket_number_str) < 10:
                pls_bucket_number_str = "0" + pls_bucket_number_str

            dts_systems.append(f"DTS-system_{pls_bucket_number_str}")
            
        else:
            other_buckets.append((i, bucket_name))

    ordered_pls = [name for _, _, name in sorted(pls_buckets, key=lambda x: (x[0], x[1]))]
    ordered_other = [name for _, name in other_buckets]
    ordered_dts = sorted(dts_systems)
    return ordered_pls + ordered_other, ordered_dts


def fetch_last_traces(session, proxy_base, bucket: str, n: int) -> str | None:

    # Set bucket schema
    measurement = "Data"
    field = "Temperature"

    # Check latest timestamp
    last_timestamp_str = influxdb.get_last_timestamp(session, proxy_base, bucket, measurement, None)
    if not last_timestamp_str:
        print(f"Could not determine last timestamp in bucket {bucket}. The bucket may be empty or the query timed out.")
        influxdb.diagnose_bucket(session, proxy_base, bucket)
        return None


    # -- Import DTS data as CSV -- #

    # Build query
    last_timestamp = datetime.fromisoformat(last_timestamp_str)

    query = influxdb.build_last_n_query(
        bucket, measurement, field, last_timestamp, n)

    # Fetch data by running query
    data_csv = influxdb.flux_query(session, proxy_base, query, debug=True)


    # -- Validate CSV -- #
    
    if not data_csv:
        print("Failed to fetch latest data as CSV from InfluxDB query.")
        print("Debug info:")
        print(f'Bucket = {bucket}')
        print(f'Last timestamp = {last_timestamp}')
        print(f'Number of requested timestamps = {n}')
        print("Failed flux query:")
        print(query)
        return None

    check_data_rows = [l for l in data_csv.splitlines() if l.strip() and not l.startswith("#")]
    if not check_data_rows:
        print("Received CSV with no data from InfluxDB query")
        return None

    return data_csv

if __name__ == "__main__":
    main()