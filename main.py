import os
import re
import ixon
from dotenv import load_dotenv
import ixon, influxdb

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
    print(buckets)

    # Get bucket schema
    bucket = buckets[0] # Temporary testing only one bucket
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


    # -- Import DTS data -- #

    # Timestamps to pull
    time_range_start = total_time_range[1]
    # time_range_end = 

    data_csv = ""

    # Validate result
    if data_csv is None:
        print("Failed to fetch CSV from InfluxDB query")
        return

    check_data_rows = [l for l in data_csv.splitlines() if l.strip() and not l.startswith("#")]
    if not check_data_rows:
        print("Received CSV with no data from InfluxDB query")
        return
    
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