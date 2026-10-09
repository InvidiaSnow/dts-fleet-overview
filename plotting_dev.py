import os
import re
import io
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import ixon, influxdb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Temporary testing debugging
from pathlib import Path



def main():
    # Dev script specific:
    CACHE = Path("cache/last_traces.csv")
    data_csv = CACHE.read_text()


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
    print(traces)


    # -- Post process data -- #
    
    # Typical noisy data due to fiberoptic connectors
    # noisy_start_length = 15

    # Calculate change per meter
    #dT = traces.diff()
    #dT.plot()
    #plt.show()

    # Try to find end of fiber


    # Trim length to relevant data


    # -- Plot data -- #

    # Scale temperature axis around median
    median_ = traces.iloc[:, -1].median() # Only newest timestamp
    axis_range = 8 # y-axis range, degrees C
    axis_offset = axis_range / 2

    print(median_)

    # Test debug - This variable exists only in main.py
    number_of_timestamps = traces.shape[1]

    # Building dynamic fading colors from grey to white
    # First is completely black, rest is [0.6 … 1>
    lightness = np.linspace(
        0.6, 1, number_of_timestamps-1, endpoint=False
    )[::-1] # Flipping around the result to match the order of the traces
    print(lightness)
    colors = ["#" + f"{round(l * 255):02x}" * 3 for l in lightness]
    colors.append("#000000")
    print(colors)

    traces.plot(color=colors)                      # one line per timestamp, Meter on the x-axis
    auto_xmin, auto_xmax, _, _  = plt.axis() # Get automatic axes
    plt.axis((auto_xmin, auto_xmax, median_-axis_offset, median_+axis_offset))
    plt.xlabel("Meter")
    plt.ylabel("Temperature (°C)")
    plt.title("Last 3 traces")
    plt.show()

    # Sub-plots

    # Display fiber length

    # Display overview with html

    # Compare to now
    # current_time = datetime.now(timezone.utc)
    
    # save_chunk(chunk_csv, folder, chunk_start, chunk_stop, system_label, raw=raw)


if __name__ == "__main__":
    main()
