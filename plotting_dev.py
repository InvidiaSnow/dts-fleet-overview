import os
import re
import io
import math
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb, to_hex
import numpy as np
import ixon, influxdb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Temporary testing debugging
from pathlib import Path


# -- Plot themes -- #

# Background of the whole window, around the subplots
FIGURE_BACKGROUND = "#4d4d4d"
TITLE_COLOR = "#ffffff"

# One theme per status. Older traces fade from "trace" towards "background".
THEMES = {
    "Live": {
        "background": "#6fcf97",  # green
        "trace": "#000000",       # newest trace
        "frame": "#000000",       # border around the plot
        "text": "#FFFFFF",        # axis labels and tick numbers
    },
    "Stale": {
        "background": "#666666",  # grey
        "trace": "#ffffff",
        "frame": "#333333",
        "text": "#FFFFFF",
    },
    "Default": {                  # used when status is None or unknown
        "background": "#ffffff",
        "trace": "#000000",
        "frame": "#000000",
        "text": "#FFFFFF",
    },
}


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


def csv_to_traces(data_csv: str) -> pd.DataFrame:
    # Convert to pandas DataFrame
    data_df = pd.read_csv(
        io.StringIO(data_csv), # io is necessary because input is not a file
        usecols=["_time", "_value", "Meter"],
        parse_dates=["_time"] # converts to datetime
        )

        # Reshape into traces
    return data_df.pivot(index="Meter", columns="_time", values="_value")

def get_traces_age(traces: pd.DataFrame) -> pd.Timedelta:
    # How recent is the most recent trace?
    current_time = pd.Timestamp.now(tz="UTC")
    trace_time = pd.Timestamp(traces.columns[-1])
    return current_time - trace_time


def plot_traces(ax, traces: pd.DataFrame, title: str, status: str | None):

    # Scale temperature axis around median
    median_ = traces.iloc[:, -1].median() # Only newest timestamp
    axis_range = 10 # y-axis range, degrees C
    axis_offset = axis_range / 2
    # Median +/- offset, but with fallback
    ylim_min = median_ - axis_offset
    ylim_max = median_ + axis_offset
    # Fallback if degC limits are out of viable range
    if median_ < 0 or median_ > 30 or ylim_min < -5 or ylim_max > 35:
        print("Automatic ylims out of range, setting default values")
        median_ = 15
        ylim_min = -5
        ylim_max = 35

    number_of_timestamps = traces.shape[1]

    # Pick colors based on status (falls back to "Default" for None/unknown)
    theme = THEMES.get(status or "Default", THEMES["Default"])
    color_traces = fading_colors(theme["trace"], theme["background"], number_of_timestamps)

    traces.plot(ax=ax, color=color_traces, legend=False)                      # one line per timestamp, Meter on the x-axis
    ax.set_ylim(ylim_min, ylim_max)
    ax.set_xlabel("Meter")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(title, color=TITLE_COLOR, fontweight="bold")

    # Apply theme colors
    ax.set_facecolor(theme["background"])
    for spine in ax.spines.values():          # the 4 border lines
        spine.set_color(theme["frame"])
        spine.set_linewidth(2.5)
    ax.tick_params(colors=theme["text"])
    ax.xaxis.label.set_color(theme["text"])
    ax.yaxis.label.set_color(theme["text"])


def fading_colors(trace_color: str, background_color: str, n: int) -> list[str]:
    """Return n hex colors, oldest to newest.

    The newest trace gets trace_color. Older traces are blended towards
    background_color, by 60% for the second newest and up to (but excluding)
    100% for the oldest, so they fade into the background.
    """
    trace = np.array(to_rgb(trace_color))            # e.g. "#000000" -> [0, 0, 0]
    background = np.array(to_rgb(background_color))

    # How far each older trace is blended towards the background: [0.6 … 1>
    fade = np.linspace(
        0.6, 1, n - 1, endpoint=False
    )[::-1] # Flipping around the result to match the order of the traces

    colors = [to_hex(tuple(trace + f * (background - trace))) for f in fade]
    colors.append(to_hex(trace_color))               # newest: full trace color
    return colors



    

def plot_overview(results: dict[str, str], ncols: int = 3):
    """Create a figure with one sub-plot for each DTS bucket result"""

    # Do some math to dynamically generate a grid of subplots
    nrows = math.ceil(len(results) / ncols)
    fig, axes = plt.subplots(nrows, ncols, squeeze=False, layout="constrained",
                             facecolor=FIGURE_BACKGROUND)

    # zip(...) pairs each subplot with one bucket and stops when the shorter of the two runs out.

    for ax, (DTS_system, data_csv) in zip(axes.flat, results.items()):
        traces = csv_to_traces(data_csv) # Pivot pre-applied to pd.DataFrame

        # Put the trace age in the plot title
        age = get_traces_age(traces)
        days = age.days
        seconds = age.seconds # Excludes whole days

        # Three different display methods depending on age
        if days > 0:
            hours = round(seconds/3600) # Round to nearest hour
            title = f"{DTS_system} - {days}d {hours}h"
        elif seconds >= 3600:
            hours = math.floor(seconds/3600) # Round down to whole hours
            minutes = round(seconds/60) - hours*60
            title = f"{DTS_system} - {hours}h {minutes}min"
        else:
            minutes = round(seconds/60)
            title = f"{DTS_system} - {minutes}min"

        if age < pd.Timedelta(minutes=4): # Compare the full age, including days
            status = "Live"
        else:
            status = "Stale"

        plot_traces(ax, traces, title, status)

    for ax in axes.flat[len(results):]:     # hide empty subplots in the last row
        ax.set_visible(False)


    fig.canvas.manager.window.state("zoomed")      # Tk (the default on Windows)
    # fig.canvas.manager.window.showMaximized()    # if you have Qt installed instead

    plt.show()                              # once, at the end

if __name__ == "__main__":
    main()
