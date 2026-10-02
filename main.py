import os
import ixon
from dotenv import load_dotenv
import ixon #, influxdb

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



    ixon_headers, devices = ixon.authenticate()
    session, proxy_base, device_name = ixon.pick_device(ixon_headers, devices, cfg)

if __name__ == "__main__":
    main()