import os
import re
import io
import math
import queue
import threading
from collections.abc import Callable
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb, to_hex
import numpy as np
import ixon, influxdb
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Temporary testing debugging
from pathlib import Path

# -- Constants -- #
LIVE_THRESHOLD_MINUTES = 4
REFRESH_MINUTES = 2.0 # How often to fetch new data when auto-refresh is on

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
    # Read results from CSV-files in the sub-folder cache/
    results = {p.stem: p.read_text() for p in Path("cache").glob("*.csv")}

    plot_overview(results)


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



    

def plot_overview(results: dict[str, str], ncols: int = 3,
                  refresh: Callable[[], dict[str, str]] | None = None):
    """Show a window with one sub-plot for each DTS system.

    If refresh is given, it is called every REFRESH_MINUTES in the background
    to fetch new results, and the plots are redrawn, until the window is closed.
    """
    fig = plt.figure(layout="constrained", facecolor=FIGURE_BACKGROUND)
    draw_overview(fig, results, ncols)

    # Keep the timers in a variable while the window is open,
    # otherwise Python deletes them and they stop
    refresh_timers = start_auto_refresh(fig, results, refresh, ncols) if refresh else None

    fig.canvas.manager.window.state("zoomed")      # Tk (the default on Windows)
    # fig.canvas.manager.window.showMaximized()    # if you have Qt installed instead

    plt.show()                              # blocks until the window is closed


def draw_overview(fig, results: dict[str, str], ncols: int = 3):
    """Draw one sub-plot per DTS system onto fig, replacing what was there."""

    # Start from an empty figure, since the number of systems may have changed
    fig.clear()

    # Do some math to dynamically generate a grid of subplots
    nrows = math.ceil(len(results) / ncols)
    axes = fig.subplots(nrows, ncols, squeeze=False)

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

        if age < pd.Timedelta(minutes=LIVE_THRESHOLD_MINUTES): # Compare the full age, including days
            status = "Live"
        else:
            status = "Stale"

        plot_traces(ax, traces, title, status)

    for ax in axes.flat[len(results):]:     # hide empty subplots in the last row
        ax.set_visible(False)

    # Show when the plots were last redrawn, in local time
    fig.suptitle(f"Updated {datetime.now():%H:%M:%S}", color=TITLE_COLOR)


def start_auto_refresh(fig, results: dict[str, str],
                       refresh: Callable[[], dict[str, str]], ncols: int):
    """Call refresh every REFRESH_MINUTES and redraw fig with the new results.

    Fetching takes a while (network), so it runs in a background thread,
    which keeps the window responsive in the meantime. Only the GUI thread
    may draw, so the background thread hands its results over through a
    queue, and a timer in the GUI thread checks that queue every second.
    """
    current_results = dict(results)   # latest data per system, updated after each fetch
    finished = queue.Queue()          # background thread -> GUI thread
    fetch_thread = None

    def fetch_in_background():
        try:
            new_results = refresh()
        except (Exception, SystemExit) as e:  # ixon.py calls sys.exit() on some errors
            print(f"Refresh failed: {e!r}")
            new_results = {}
        finished.put(new_results)

    def start_fetch():
        nonlocal fetch_thread  # lets this inner function replace the variable above
        if fetch_thread and fetch_thread.is_alive():
            return  # previous fetch is still running, skip this round
        print(f"\nRefreshing data ({datetime.now():%H:%M:%S})...")
        # daemon=True: don't keep the program running after the window is closed
        fetch_thread = threading.Thread(target=fetch_in_background, daemon=True)
        fetch_thread.start()

    def redraw_if_finished():
        try:
            new_results = finished.get_nowait()
        except queue.Empty:
            return  # nothing new yet
        # Systems that failed this time keep their old data, so their age
        # keeps growing and they turn "Stale" instead of disappearing
        current_results.update(new_results)
        draw_overview(fig, current_results, ncols)
        fig.canvas.draw_idle()

    # Timers run their callback in the GUI thread while plt.show() is running
    fetch_timer = fig.canvas.new_timer(interval=REFRESH_MINUTES * 60 * 1000)  # milliseconds
    fetch_timer.add_callback(start_fetch)
    fetch_timer.start()

    check_timer = fig.canvas.new_timer(interval=1000)
    check_timer.add_callback(redraw_if_finished)
    check_timer.start()

    return fetch_timer, check_timer

if __name__ == "__main__":
    main()
