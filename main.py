import os
import re
import io
import pandas as pd
import matplotlib.pyplot as plt
import ixon, influxdb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

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
    buckets = sort_buckets_for_display(buckets)

    bucket = buckets[5] # Temporary testing only one bucket

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
        return


    # -- Import DTS data as CSV -- #

    # Build query
    last_timestamp_str = total_time_range[1]
    last_timestamp = datetime.fromisoformat(last_timestamp_str)
    number_of_timestamps = 3

    query = influxdb.build_last_n_query(
        bucket, measurement, field, last_timestamp, number_of_timestamps)

    # Fetch data by running query
    print(f"    Fetching data from the {number_of_timestamps} latest timestamps...")

    data_csv = influxdb.flux_query(session, proxy_base, query, debug=True)


    # -- Validate and format DTS data -- #
    
    # Validate CSV output
    if data_csv:
        print(f"Fetched data")
    else:
        print("Failed to fetch latest data as CSV from InfluxDB query.")
        print("Debug info:")
        print(f'Bucket = {bucket}')
        print(f'Last timestamp = {last_timestamp}')
        print(f'Number of requested timestamps = {number_of_timestamps}')
        print("Failed flux query:")
        print(query)
        return

    if len(data_csv) >= 1000:
        print(data_csv[0:1000])

    check_data_rows = [l for l in data_csv.splitlines() if l.strip() and not l.startswith("#")]
    if not check_data_rows:
        print("Received CSV with no data from InfluxDB query")
        return

    # Format data from CSV

    # Convert to pandas DataFrame
    data_df = pd.read_csv(
        io.StringIO(data_csv), # io is necessary because input is not a file
        usecols=["_time", "_value", "Meter"],
        parse_dates=["_time"] # converts to datetime
        )

    print("pandas DataFrame:")
    print(data_df)

    # Reshape into traces
    traces = data_df.pivot(index="Meter", columns="_time", values="_value")


    # -- Post process data -- #

    # Calculate change per meter
    dT = traces.diff()
    dT.plot()
    plt.show()

    # -- Plot data -- #
"""
    traces.plot()                      # one line per timestamp, Meter on the x-axis
    plt.xlabel("Meter")
    plt.ylabel("Temperature (°C)")
    plt.title("Last 3 traces")
    plt.show()"""

    # Compare to now
    # current_time = datetime.now(timezone.utc)
    
    # save_chunk(chunk_csv, folder, chunk_start, chunk_stop, system_label, raw=raw)


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

if __name__ == "__main__":
    main()