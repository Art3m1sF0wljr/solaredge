import subprocess
import time
from datetime import datetime
import re

# Database file path
DB_FILE = "solar_edge_data.log"

def run_app_py():
    """Run app.py and capture its output while displaying it live."""
    try:
        process = subprocess.Popen(['python3', 'app.py'],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 text=True)

        # Capture and display output in real-time
        output_lines = []
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(line.strip())  # Display the live output
                output_lines.append(line)

        return ''.join(output_lines)
    except Exception as e:
        print(f"Error running app.py: {e}")
        return None

def parse_output(output):
    """Parse the output of app.py and extract relevant data."""
    data = {
        'timestamp': datetime.now().isoformat(),
        'ac_power': None,
        'dc_power': None,
        'state': None,
        'energy': None
    }

    # Extract AC Power
    ac_power_match = re.search(r'Power:\s+([\d.]+)\s+W', output)
    if ac_power_match:
        data['ac_power'] = float(ac_power_match.group(1))

    # Extract DC Power
    dc_power_match = re.search(r'Power:\s+([\d.]+)\s+W', output.split('=== DC Measurements ===')[1])
    if dc_power_match:
        data['dc_power'] = float(dc_power_match.group(1))

    # Extract State
    state_match = re.search(r'State:\s+([^\n]+)', output)
    if state_match:
        data['state'] = state_match.group(1).strip()

    # Extract Energy
    energy_match = re.search(r'Energy:\s+([\d.]+)\s+MWh', output)
    if energy_match:
        data['energy'] = float(energy_match.group(1))

    return data

def save_to_database(data):
    """Append data to the database text file."""
    with open(DB_FILE, 'a') as f:
        f.write(f"{data['timestamp']}, "
                f"AC Power: {data['ac_power']} W, "
                f"DC Power: {data['dc_power']} W, "
                f"State: {data['state']}, "
                f"Energy: {data['energy']} MWh\n")

def main():
    print("SolarEdge Data Logger started. Press Ctrl+C to stop.")
    print(f"Data will be saved to {DB_FILE}\n")

    try:
        while True:
            # Run app.py and process its output
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching data...")
            output = run_app_py()

            if output:
                data = parse_output(output)
                save_to_database(data)
                print(f"\n[{data['timestamp']}] Data logged successfully")

            # Wait for 1 minute
            print(f"\nWaiting for next reading in 60 seconds...")
            for remaining in range(60, 0, -1):
                print(f"\rNext reading in: {remaining:2d} seconds", end='')
                time.sleep(1)
            print()

    except KeyboardInterrupt:
        print("\n\nSolarEdge Data Logger stopped.")

if __name__ == "__main__":
    main()
