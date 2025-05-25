import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import os
from matplotlib.animation import FuncAnimation

# Configuration
LOG_FILE = "/home/pi/program/solaredge/solar_edge_data.log"
UPDATE_INTERVAL = 600  # 10 minutes in seconds
PLOT_DAYS = 3  # Number of days to display
SMOOTHING_WINDOW = 5  # Points for moving average smoothing

def parse_log_file():
    """Parse the log file into a pandas DataFrame with proper types"""
    data = []
    if not os.path.exists(LOG_FILE):
        print(f"Warning: Log file {LOG_FILE} not found!")
        return pd.DataFrame(columns=['timestamp', 'ac_power', 'dc_power', 'state', 'energy'])

    with open(LOG_FILE, 'r') as f:
        for line in f:
            try:
                parts = line.strip().split(', ')
                if len(parts) < 5:
                    continue

                timestamp = datetime.fromisoformat(parts[0])

                # Extract values with error handling
                ac_power = float(parts[1].split(': ')[1].split(' ')[0])
                dc_power = float(parts[2].split(': ')[1].split(' ')[0])
                state = parts[3].split(': ')[1]
                energy = float(parts[4].split(': ')[1].split(' ')[0]) * 1000  # Convert MWh to kWh

                data.append({
                    'timestamp': timestamp,
                    'ac_power': ac_power,
                    'dc_power': dc_power,
                    'state': state,
                    'energy': energy
                })
            except Exception as e:
                print(f"Error parsing line: {line}\n{str(e)}")
                continue

    if not data:
        return pd.DataFrame(columns=['timestamp', 'ac_power', 'dc_power', 'state', 'energy'])

    return pd.DataFrame(data)

def calculate_energy_derivative(df):
    """Calculate power from energy differences with proper handling of non-uniform time steps"""
    if df.empty:
        df['power_from_energy'] = []
        df['power_from_energy_smoothed'] = []
        return df

    df = df.sort_values('timestamp').copy()

    # Calculate time differences in seconds
    time_deltas = df['timestamp'].diff().dt.total_seconds()

    # Calculate energy differences in Wh (since energy is in kWh in the log)
    energy_deltas = df['energy'].diff() * 1000  # Convert kWh to Wh

    # Calculate power in W (Watts) using the actual time differences
    df['power_from_energy'] = energy_deltas / (time_deltas / 3600)  # Convert seconds to hours for Wh→W

    # Handle invalid values
    df['power_from_energy'] = df['power_from_energy'].fillna(0)
    df.loc[~np.isfinite(df['power_from_energy']), 'power_from_energy'] = 0

    # Add smoothing
    df['power_from_energy_smoothed'] = (
        df['power_from_energy']
        .rolling(window=SMOOTHING_WINDOW, min_periods=1, center=True)
        .mean()
    )

    return df

def filter_last_days(df, days=3):
    """Filter data to only include the last N days"""
    if df.empty:
        return df
    cutoff = datetime.now() - timedelta(days=days)
    return df[df['timestamp'] >= cutoff].copy()

def init_plot():
    """Initialize the plot with empty data"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    return fig, ax1, ax2

def update_plots(frame):
    """Callback function for animation that updates the plots"""
    try:
        # Get data
        df = parse_log_file()
        df = filter_last_days(df, PLOT_DAYS)
        df = calculate_energy_derivative(df)

        # Get the figure and axes
        fig = plt.gcf()
        ax1, ax2 = fig.get_axes()

        # Clear existing plots
        ax1.clear()
        ax2.clear()

        # Update title
        update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        fig.suptitle(f'SolarEdge Power Monitor - Last Updated: {update_time}')

        if df.empty:
            # Show empty plot message
            for ax in [ax1, ax2]:
                ax.text(0.5, 0.5, 'Waiting for data...',
                       ha='center', va='center', transform=ax.transAxes)
                ax.set_xticks([])
                ax.set_yticks([])
            return

        # Plot 1: AC and DC Power
        ax1.plot(df['timestamp'], df['ac_power']/1000,
                label='AC Power (kW)', color='blue', alpha=0.7, linewidth=1.5)
        ax1.plot(df['timestamp'], df['dc_power']/1000,
                label='DC Power (kW)', color='green', alpha=0.7, linewidth=1.5)
        ax1.set_ylabel('Power (kW)')
        ax1.set_title(f'Direct Power Measurements (Last {PLOT_DAYS} Days)')
        ax1.legend(loc='upper left')
        ax1.grid(True, which='both', linestyle='--', alpha=0.7)
        ax1.set_ylim(0, 5)

        # Plot 2: Power calculated from energy derivative
        if 'power_from_energy' in df.columns:
            ax2.plot(df['timestamp'], df['power_from_energy']/1000,
                    label='Instantaneous Power', color='red', alpha=0.3, linewidth=1)
            ax2.plot(df['timestamp'], df['power_from_energy_smoothed']/1000,
                    label=f'Smoothed (window={SMOOTHING_WINDOW})', color='red', linewidth=2)
            ax2.set_ylabel('Power (kW)')
            ax2.set_xlabel('Time')
            ax2.set_title('Power Calculated from Energy Differences (ΔE/Δt)')
            ax2.legend(loc='upper left')
            ax2.grid(True, which='both', linestyle='--', alpha=0.7)
            ax2.axhline(0, color='black', linestyle='-', alpha=0.3)
            ax2.set_ylim(0, 5)

        # Set common x-axis limits based on data range
        xmin = df['timestamp'].min()
        xmax = df['timestamp'].max()
        for ax in [ax1, ax2]:
            ax.set_xlim(xmin, xmax)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

        plt.tight_layout()

    except Exception as e:
        print(f"Error updating plots: {str(e)}")

def main():
    print("SolarEdge Power Monitor starting...")
    print(f"Reading data from: {LOG_FILE}")
    print(f"Update interval: {UPDATE_INTERVAL} seconds")
    print(f"Displaying last {PLOT_DAYS} days of data")

    # Create initial figure
    fig, ax1, ax2 = init_plot()

    # Initial empty plot
    for ax in [ax1, ax2]:
        ax.text(0.5, 0.5, 'Loading data...',
               ha='center', va='center', transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])

    # Set up animation
    ani = FuncAnimation(fig, update_plots, interval=UPDATE_INTERVAL*1000)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
