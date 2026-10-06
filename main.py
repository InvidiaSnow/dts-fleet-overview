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

    # Authenticate Ixon login
    ixon_headers, ixon_devices = ixon.authenticate()

    # Start a WebAccess proxy session
    session, proxy_base = ixon.start_session(ixon_headers, ixon_devices, cfg)

    # DTS buckets
    ## Each DTS has it's own bucket in InfluxDB

    print("  Fetching DTS buckets...")
    buckets = influxdb.list_buckets(session, proxy_base)
    if not buckets:
        print("Could not list buckets.")
        return
    buckets = sort_buckets_for_display(buckets)
    print(buckets)

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

if __name__ == "__main__":
    main()