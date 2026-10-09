import os
import re
import io
import math
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
    results = {p.stem: p.read_text() for p in Path("cache").glob("*.csv")}

    plot_overview(results)

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


    # Display fiber length

    # Display overview with html

    # Compare to now
    # current_time = datetime.now(timezone.utc)

def csv_to_traces(data_csv: str) -> pd.DataFrame:
    # Convert to pandas DataFrame
    data_df = pd.read_csv(
        io.StringIO(data_csv), # io is necessary because input is not a file
        usecols=["_time", "_value", "Meter"],
        parse_dates=["_time"] # converts to datetime
        )

        # Reshape into traces
    return data_df.pivot(index="Meter", columns="_time", values="_value")

def plot_traces(ax, traces: pd.DataFrame, title: str):

    # Scale temperature axis around median
    median_ = traces.iloc[:, -1].median() # Only newest timestamp
    axis_range = 8 # y-axis range, degrees C
    axis_offset = axis_range / 2

    number_of_timestamps = traces.shape[1]

    # Building dynamic fading colors from grey to white
    # First is completely black, rest is [0.6 … 1>
    lightness = np.linspace(
        0.6, 1, number_of_timestamps-1, endpoint=False
    )[::-1] # Flipping around the result to match the order of the traces
    print(lightness)
    colors = ["#" + f"{round(l * 255):02x}" * 3 for l in lightness]
    colors.append("#000000")

    traces.plot(ax=ax, color=colors, legend=False)                      # one line per timestamp, Meter on the x-axis
    ax.set_ylim(median_ - axis_offset, median_ + axis_offset)
    ax.set_xlabel("Meter")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(title)

def plot_overview(results: dict[str, str], ncols: int = 3):
    """Create a figure with one sub-plot for each DTS bucket result"""

    # Do some math to dynamically generate a grid of subplots
    nrows = math.ceil(len(results) / ncols)
    fig, axes = plt.subplots(nrows, ncols, squeeze=False, layout="constrained")

    # zip(...) pairs each subplot with one bucket and stops when the shorter of the two runs out.

    for ax, (bucket, data_csv) in zip(axes.flat, results.items()):
        traces = csv_to_traces(data_csv)
        plot_traces(ax, traces, bucket)

    for ax in axes.flat[len(results):]:     # hide empty subplots in the last row
        ax.set_visible(False)


    fig.canvas.manager.window.state("zoomed")      # Tk (the default on Windows)
    # fig.canvas.manager.window.showMaximized()    # if you have Qt installed instead

    plt.show()                              # once, at the end

if __name__ == "__main__":
    main()
