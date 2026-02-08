### EC info collector - console (CLI) + GE (SCP) + Display
# v6.0.7: Fixed bug where filenames used MAC when an IP was provided.
# v6.0.6: Added --ip, --mac, and --domain command-line arguments to override config values.
# v6.0.5: Added validation to check if the 'ec_pnm_stats' command executed successfully
#         before attempting to process the output file.
# v6.0.4: Changed peak detection from 10 to 12 most prominent peaks.
# v6.0.3: Added automatic peak detection in the time-domain plot.
# v6.0.2: Modified continuous mode to append new data as columns instead of rows.
# v6.0.1: Updated to append data to CSV files instead of overwriting.
# v6.0.0: Refactored to use a unified config manager and amp library.
# V6.0.8: V6.0.7 code base.  Added error handling for jump connection.
#         changed plotting to use plotly and save plots as interactive html.
#
#   Sample node: PADUSTES4A
#   Sapmle Amp Name UNREG-PADUSTEST4-24:A1:86:1F:F3:AC
#   Sample MAC 24:a1:86:1f:f3:ac
#   Sample IP  2001:0558:6031:001C:3408:5385:73EF:FE58

#   Sample node: INSPD07C0A 
#   Sapmle Amp Name INSPD07C0AAA012
#   Sample MAC 24:a1:86:0e:23:74
#   Sample IP  2001:0558:600D:0054:F46C:6243:77E6:32D1

''' example usages:
python ec.py --image CC --domain PROD --mac 24:a1:86:1f:f3:ac
python ec.py --image CC --domain PROD --ip 2001:0558:600D:0054:F46C:6243:77E6:32D1 --path PADUSTES4A/24a1861ff3ac/20260208_1338
'''

import paramiko
import sys
from paramiko import SSHClient
from scp import SCPClient, SCPException
import os
import csv
import re
import subprocess
import time
import ipaddress
import argparse
import numpy as np
from itertools import zip_longest
from scipy.signal import find_peaks
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

# New unified library imports
import ec_config_manager
import amp_library

# --- Command-line argument parsing and conditional imports ---
parser = argparse.ArgumentParser(description='FDX-AMP Echo Cancellation Data Collector.')
parser.add_argument('--image', type=str, choices=['CS', 'CC', 'SC', 'BC', 'CCs'], required=True,
                    help='Specify the image type: CS (CommScope), CC (Comcast), SC (Sercomm), or BC (Broadcom).')
parser.add_argument('--time-axis', type=str, choices=['time', 'distance'], default='distance',
                    help='Specify the x-axis for the time-domain plot: time (us) or distance (ft).')
parser.add_argument('--no-jump', action='store_true',
                    help='Skip the jump server and connect directly to the target device.')
# --- New arguments added ---
parser.add_argument('--mac', type=str, help="Optional. Target device MAC address. Overrides the value in config.")
parser.add_argument('--ip', type=str, help="Optional. Target device IP address. Overrides the value in config and any MAC-based IP lookup.")
parser.add_argument('--domain', type=str, help="Optional. CM domain for IP lookup script. Overrides the value in config.")
parser.add_argument('--path', type=str, help="Optional. Path for output files. Overrides the value in config.")
# --- New argument for cancellation depth ---
parser.add_argument('--show-cancellation-depth', action='store_true', default=False,
                    help="Include Cancellation Depth in plots and CSVs (default: not shown).")

args = parser.parse_args()


# --- Load Configuration and Instantiate Amp Controller ---
try:
    config = ec_config_manager.CONFIGURATIONS[args.image]
    if args.image == 'CS':
        amp = amp_library.CommscopeAmp()
    elif args.image == 'CC' or args.image == 'CCs':
        amp = amp_library.ComcastAmp()
    elif args.image == 'SC':
        amp = amp_library.SercommAmp()
    elif args.image == 'BC':
        amp = amp_library.BroadcomAmp()
except KeyError:
    print(f"FATAL: Configuration for image type '{args.image}' not found in ec_config_manager.py.")
    sys.exit(1)
except (ImportError, AttributeError) as e:
    print(f"FATAL: Could not load the required library for '{args.image}'. Error: {e}")
    sys.exit(1)

print(f"Running with {args.image} image configuration...")

def run_script_and_get_result(script_path, arguments=[]):
  """Runs a Python script in a subprocess and returns the output."""
  try:
    command = ["python", script_path] + arguments
    process = subprocess.run(command, capture_output=True, text=True, check=True)
    return process.stdout.strip()
  except (subprocess.CalledProcessError, FileNotFoundError) as e:
    print(f"Error running script {script_path}: {e}")
    return None

def is_ipv6(address):
  """Checks if a string is a valid IPv6 address."""
  try:
    ipaddress.IPv6Address(address)
    return True
  except ipaddress.AddressValueError:
    return False

def is_ipv4(address):
  """Checks if a string is a valid IPv4 address."""
  try:
    ipaddress.IPv4Address(address)
    return True
  except ipaddress.AddressValueError:
    return False

def scp_get_with_retry(scp_client, remote_path, local_path, retries=3, delay=3):
    """Attempts to download a file using SCP, with a retry mechanism."""
    for attempt in range(retries):
        try:
            print(f"Attempting to download '{remote_path}' (Attempt {attempt + 1}/{retries})...")
            scp_client.get(remote_path, local_path)
            print(f"Successfully downloaded '{remote_path}' to '{local_path}'.")
            return True
        except SCPException as e:
            print(f"SCP Error on attempt {attempt + 1}: {e}. File may not exist on remote.")
            if "No such file or directory" in str(e):
                print(str(e))
                #return False
            if attempt < retries - 1:
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                print(f"Failed to download '{remote_path}' after {retries} attempts.")
        except Exception as e:
            print(f"An unexpected error occurred during SCP download on attempt {attempt + 1}: {e}")
            if attempt < retries - 1:
                print(f"Waiting {delay} seconds before retrying...")
                time.sleep(delay)
            else:
                print(f"Failed to download '{remote_path}' due to an unexpected error.")

    return False

def save_trace_to_csv(filepath, headers, x_data, y_data, run_single):
    """Saves trace data to a CSV file.
    In single-run mode, it creates a new file.
    In continuous mode, it appends the new y_data as a new column.
    """
    if not y_data:
        return

    file_exists = os.path.exists(filepath)

    if run_single or not file_exists:
        if not x_data:
             print(f"Warning: Cannot create new CSV {filepath} without x_data.")
             return
        try:
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                timestamp_header = f"{headers[1]}_{time.strftime('%Y%m%d_%H%M%S')}"
                writer.writerow([headers[0], timestamp_header])
                writer.writerows(zip(x_data, y_data))
        except Exception as e:
            print(f"Error writing new CSV to {filepath}: {e}")
        return

    try:
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f)
            existing_rows = list(reader)

        if not existing_rows:
             save_trace_to_csv(filepath, headers, x_data, y_data, True)
             return

        new_y_header = f"{headers[1]}_{time.strftime('%Y%m%d_%H%M%S')}"
        existing_rows[0].append(new_y_header)

        num_data_rows = len(existing_rows) - 1
        for i in range(num_data_rows):
            new_value = y_data[i] if i < len(y_data) else ''
            existing_rows[i+1].append(new_value)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(existing_rows)

    except Exception as e:
        print(f"Error updating CSV {filepath} by adding a column: {e}")

# --- Modified Section: Override config with command-line arguments ---
# Config parameters (defaults from config file)
target_cm_mac = config['target_ecm_mac']
target_hostname = config['target_hostname']
cm_domain = config['cm_domain']
# path = config['path']
path = "./output/" +args.path+"/ec" # Use command-line path if provided
run_single = config['run_single']
lstatType = list(config['statType']) # Make a mutable copy
lsubBandId = config['subBandId']

# Override with command-line arguments if provided
if args.mac:
    target_cm_mac = args.mac
    print(f"Using MAC address from command line: {target_cm_mac}")

if args.domain:
    cm_domain = args.domain
    print(f"Using CM domain from command line: {cm_domain}")

if args.ip:
    target_hostname = args.ip
    print(f"Using IP address from command line: {target_hostname}")
elif target_cm_mac:
    print(f"Looking up IP for MAC: {target_cm_mac}")
    script = os.path.join(config['get_ip_path'], config['get_ip_script'])
    arguments = [cm_domain, "CPE", target_cm_mac]
    temp = run_script_and_get_result(script, arguments)
    if temp and (is_ipv4(temp) or is_ipv6(temp)):
        target_hostname = temp
        print(f"Found IP: {target_hostname}")
    else:
        print(f"Could not find a valid IP for MAC {target_cm_mac}. Will use hostname from config: {target_hostname}")
# --- End of Modified Section ---

if 2 in lstatType:
    print("Note: Removing statType 2. Time-domain data will be derived via IFFT.")
    lstatType.remove(2)

# --- BUG FIX: Use IP for filename if provided, otherwise use MAC ---
if args.ip:
    # Sanitize IP address for use in filenames
    clean_identifier = args.ip.replace(".", "-").replace(":", "_")
    identifier_suffix = f"_{clean_identifier}"
elif target_cm_mac:
    # Sanitize MAC address for use in filenames
    clean_identifier = target_cm_mac.replace(":", "").replace("-", "")
    identifier_suffix = f"_{clean_identifier}"
else:
    identifier_suffix = "" # No identifier if neither is available

# --- Ensure identifier_suffix is safe for filenames (Windows) ---
def sanitize_filename_component(s):
    # Allow only alphanumeric, dash, and underscore
    return re.sub(r'[^A-Za-z0-9_\-]', '', s)

identifier_suffix = sanitize_filename_component(identifier_suffix)
# --- End of BUG FIX ---

os.makedirs(path, exist_ok=True)

# Plotting setup
plot_coef_window = True
plot_psd_window = True
plot_rl_trace = False
plot_rxsnr_trace = False
# --- Control whether to plot cancellation depth ---
plot_cancellation_depth = args.show_cancellation_depth

# --- Plotly Figure Setup ---
fig_coef = None
fig_psd = None
plot_lines = []
peak_marker_trace = None

if plot_coef_window:
    # Create a subplot with 1 row and 2 columns: left for time coef, right for freq coef
    fig_coef = make_subplots(
        rows=1, cols=2,
        column_widths=[0.7, 0.3],
        horizontal_spacing=0.08,
        subplot_titles=("Time Coef (IFFT, all channels)", "Freq Coef (all sub-bands)")
    )
    fig_coef.update_layout(
        title=f'Echo Cancellation Coefficients{identifier_suffix}',
        height=800,
        width=1600,
        template='plotly_white',
        legend=dict(
            bordercolor="black",
            borderwidth=2
        ),
        margin=dict(l=60, r=60, t=80, b=60),
        paper_bgcolor='white',
        plot_bgcolor='white',
        shapes=[
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=0,
                y0=0,
                x1=1,
                y1=1,
                line=dict(
                    color="black",
                    width=3
                ),
                fillcolor='rgba(0,0,0,0)',
                layer="below"
            )
        ]
    )
    # Time Domain traces (6 channels) in left subplot (col=1)
    for ch in range(6):
        fig_coef.add_trace(
            go.Scatter(x=[], y=[], mode='lines', name=f"Time Coef ch{ch} (IFFT)", legendgroup="time"),
            row=1, col=1
        )
    # Peak marker trace in left subplot (col=1)
    fig_coef.add_trace(
        go.Scatter(x=[], y=[], mode='markers', marker=dict(color='red', size=10, symbol='x'), name='Detected Peaks', legendgroup="peaks"),
        row=1, col=1
    )
    # Frequency Domain trace in right subplot (col=2)
    fig_coef.add_trace(
        go.Scatter(x=[], y=[], mode='lines', name="Freq Coef (all sub-bands)", legendgroup="freq"),
        row=1, col=2
    )
    # Axis labels
    fig_coef.update_yaxes(title_text="Magnitude (dB)", row=1, col=1)
    fig_coef.update_xaxes(title_text="Time(us) / Distance(ft)", row=1, col=1)
    fig_coef.update_yaxes(title_text="Magnitude (dB)", row=1, col=2)
    fig_coef.update_xaxes(
        title_text="Frequency(MHz)",
        row=1, col=2,
        dtick=96,      # Set major grid interval to 96 MHz for Freq Coef
        tick0=204      # Start major grid at 204 MHz for Freq Coef
    )

if plot_psd_window:
    fig_psd = go.Figure()
    fig_psd.update_layout(
        title=f'EC PSD and Derived Metrics{identifier_suffix}',
        height=900,
        width=1600,
        template='plotly_white',
        legend=dict(
            bordercolor="black",
            borderwidth=2
        ),
        margin=dict(l=60, r=60, t=80, b=60),
        paper_bgcolor='white',
        plot_bgcolor='white',
        shapes=[
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=0,
                y0=0,
                x1=1,
                y1=1,
                line=dict(
                    color="black",
                    width=3
                ),
                fillcolor='rgba(0,0,0,0)',
                layer="below"
            )
        ]
    )
    # Only add cancellation depth line if enabled
    if plot_cancellation_depth:
        fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="EC Cancellation Depth"))
    fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="Echo PSD"))
    fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="Residual Echo PSD"))
    fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="Downstream PSD"))
    fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="Upstream PSD"))
    if plot_rl_trace:
        fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="Return Loss"))
    if plot_rxsnr_trace:
        fig_psd.add_trace(go.Scatter(x=[], y=[], mode='lines', name="Upstream Rx SNR"))
    fig_psd.update_xaxes(
        title_text="Frequency(MHz)",
        range=[108.0, None],
        dtick=96.0,      # Set major grid interval to 96.0 MHz
        tick0=204.0      # Start major grid at 204 MHz
    )
    fig_psd.update_yaxes(title_text="Power(dBmV/100kHz) or dB", range=[-80, None])  # Set min Y to -80dB

# Remove any line like:
# fig_coef.layout.responsive = True
# or
# fig_psd.layout.responsive = True

# If you want responsive resizing, use pio.show(fig, config={"responsive": True}) when displaying,
# but do NOT set a 'responsive' property on the layout object itself.

# --- SSH Connection Logic ---
if not args.no_jump:
    print("--- Starting Data Collection Cycle (via Jump Server) ---")
    jumpbox_client = paramiko.SSHClient()
    jumpbox_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        jumpbox_client.connect(config['jumpbox_hostname'], username=config['jumpbox_username'])
    except Exception as e:
        # print("\a")  # Play beep sound
        print("\nJumpbox Connect Failed, make sure you are freshly authenticated!\n")
        print(f"Error details: {e}")
        sys.exit(1)
    transport = jumpbox_client.get_transport()
    dest_addr = (target_hostname, 22)
    jumpbox_channel = transport.open_channel("direct-tcpip", dest_addr, ('', 0))
    target_client = paramiko.SSHClient()
    target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    target_client.connect(target_hostname, username=config['target_username'], password=config['target_password'], sock=jumpbox_channel)
else:
    print("--- Starting Data Collection Cycle (Direct Connection) ---")
    target_client = paramiko.SSHClient()
    target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    target_client.connect(target_hostname, username=config['target_username'], password=config['target_password'])

channel = target_client.invoke_shell(); channel.settimeout(1000)
target_scp_client = SCPClient(target_client.get_transport())

while True:
    num_of_stattype = 11
    num_of_subband = 3
    data = [[[] for _ in range(num_of_subband)] for _ in range(num_of_stattype)]
    freq = [[[] for _ in range(num_of_subband)] for _ in range(num_of_stattype)]
    freq_coef_complex = [[] for _ in range(num_of_subband)]
    num_bins_per_subband = [0] * num_of_subband
    # Initialize lists to hold peak data for the current cycle
    all_peak_x = []
    all_peak_y = []

    try:
        if config['rfboard_commands']:
            ret = ""
            filename = f"rfboard{identifier_suffix}{config['result_filename_appendix']}.txt"
            print(f"Filename: {filename}")
            with open(os.path.join(path, filename), 'w') as f:
                for command in config['rfboard_commands']:
                    ret += amp.rf_comm(channel, command)
                lines = ret.splitlines()
                lines = [line.strip() for line in lines if line.strip()]
                cleaned_string = '\n'.join(lines)
                f.write(cleaned_string)
                print(f"Successfully wrote to {filename}")

        if config['hal_commands']:
            ret = ""
            filename = f"hal{identifier_suffix}{config['result_filename_appendix']}.txt"
            print(f"Filename: {filename}")
            with open(os.path.join(path, filename), 'w') as f:
                for command in config['hal_commands']:
                    ret += amp.hal_comm(channel, command, "InputPower")
                lines = ret.splitlines()
                lines = [line.strip() for line in lines if line.strip()]
                cleaned_string = '\n'.join(lines)
                f.write(cleaned_string)
                print(f"Successfully wrote to {filename}")

        for statsType in lstatType:
            for subBandId in lsubBandId:
                filename = f"EC_{statsType}_{subBandId}.dat"
                print(f"Requesting: {filename}")
                command = f"ec_pnm_stats {statsType} {subBandId} /tmp/{filename}"
                command_output = amp.hal_comm(channel, command)

                # NEW: Validate command output before proceeding
                info_count = command_output.upper().count('INFO')
                fail_present = 'FAIL' in command_output.upper()

                if info_count >= 2 and not fail_present:
                    print(f"Command '{command}' executed successfully.")

                    if statsType == 8:
                        time.sleep(2)
                    else:
                        time.sleep(1)

                    source = f"/tmp/{filename}"
                    destination = f'{path}/{filename}'

                    if not scp_get_with_retry(target_scp_client, source, destination):
                        print(f"Could not retrieve {filename}. Skipping this file.")
                        continue

                    print(f"Decoding file: {destination}")
                    with open(destination, 'r') as file:
                        reader = csv.reader(file)
                        temp_statType, temp_numBins, temp_startFreq, temp_subBand = -1, 0, 0, -1
                        real, imag = [], []
                        temp_data = []

                        for row in reader:
                            match_stat = re.search(r"StatType:(\d+)", str(row));
                            if match_stat: temp_statType = int(match_stat.group(1)); continue

                            match_bins = re.search(r"NumBins:(\d+)", str(row))
                            if match_bins: temp_numBins = int(match_bins.group(1)); continue

                            match_freq = re.search(r"StartFreq:(\d+)", str(row))
                            if match_freq: temp_startFreq = int(match_freq.group(1)); continue

                            if "PerBin" in str(row): continue

                            if temp_subBand == -1 and temp_startFreq > 0:
                                 temp_subBand = 0 if temp_startFreq < 150e6 else 2 if temp_startFreq > 450e6 else 1
                                 num_bins_per_subband[temp_subBand] = temp_numBins

                            temp_data.append(row)

                        if temp_subBand != -1:
                            actual_num_bins = len(temp_data)
                            if actual_num_bins < temp_numBins:
                                print(f"  WARNING: Incomplete file '{filename}'. Expected {temp_numBins} bins, found {actual_num_bins}.")
                                temp_numBins = actual_num_bins

                            for row in temp_data:
                                if temp_statType == 1:
                                    r_val, i_val = float(row[0]), float(row[1])
                                    real.append(r_val); imag.append(i_val)
                                else:
                                    value = float(row[0])
                                    data[temp_statType][temp_subBand].append(max(value, -60) if temp_statType == 8 else value)

                            if temp_statType == 1:
                                data[temp_statType][temp_subBand] = amp.complex_to_mag_db(real, imag)
                                freq_coef_complex[temp_subBand] = [complex(r, i) for r, i in zip(real, imag)]

                            for i in range(temp_numBins):
                                freq[temp_statType][temp_subBand].append(temp_startFreq / 1e6 + i / 10)

                    # --- Live Plot Updates ---
                    print("Updating plots...")

                    def safe_plotly_update(fig, trace_idx, x, y, row=None, col=None):
                        if fig is None or len(fig.data) <= trace_idx:
                            return
                        # For subplots, use update_traces with selector and row/col
                        if row is not None and col is not None and hasattr(fig, "update_traces"):
                            fig.update_traces(
                                selector=dict(name=fig.data[trace_idx].name),
                                x=x, y=y, row=row, col=col
                            )
                        else:
                            fig.data[trace_idx].x = x
                            fig.data[trace_idx].y = y

                    if plot_coef_window:
                        # Time Coef traces (ch0-ch5) are traces 0-5 in col=1
                        if statsType == 1 and any(freq_coef_complex):
                            for i in range(num_of_subband):
                                if not freq_coef_complex[i]: continue
                                subband_data = freq_coef_complex[i]
                                expected_bins = num_bins_per_subband[i]
                                actual_bins = len(subband_data)
                                channel_freq_data = []
                                channel_indices = []
                                if actual_bins < (expected_bins * 0.75) and actual_bins > 0:
                                    channel_freq_data = [subband_data]
                                    channel_indices = [i * 2]
                                elif actual_bins > 0:
                                    midpoint = actual_bins // 2
                                    channel_freq_data = [subband_data[:midpoint], subband_data[midpoint:]]
                                    channel_indices = [i * 2, i * 2 + 1]
                                for j, channel_data in enumerate(channel_freq_data):
                                    if not channel_data: continue
                                    channel_index = channel_indices[j]
                                    if channel_index >= 6: continue
                                    time_domain = np.fft.ifft(channel_data)
                                    with np.errstate(divide='ignore'):
                                        time_domain_db = 20 * np.log10(np.abs(time_domain))
                                    time_domain_db[np.isneginf(time_domain_db)] = -100
                                    plot_len = len(channel_data) // 2
                                    round_trip_time_us = np.array([k * (5 / plot_len) for k in range(plot_len)]) if plot_len > 0 else np.array([])
                                    one_way_time_us = round_trip_time_us / 2.0
                                    if args.time_axis == 'distance':
                                        velocity_of_propagation = 0.87
                                        speed_of_light_ft_per_ns = 0.983571056
                                        one_way_time_ns = one_way_time_us * 1000
                                        xtime = one_way_time_ns * velocity_of_propagation * speed_of_light_ft_per_ns
                                    else:
                                        xtime = one_way_time_us
                                    y_data = time_domain_db[:plot_len]
                                    xtime_shifted = xtime
                                    if len(y_data) > 0:
                                        peaks, _ = find_peaks(y_data, height=-50, prominence=1)
                                        if len(peaks) > 0:
                                            prominent_peaks = sorted(peaks, key=lambda p: y_data[p], reverse=True)[:12]
                                            first_prominent_peak = sorted(prominent_peaks)[0]
                                            time_shift = xtime[first_prominent_peak]
                                            xtime_shifted = xtime - time_shift
                                            all_peak_x.extend(xtime_shifted[prominent_peaks])
                                            all_peak_y.extend(y_data[prominent_peaks])
                                    safe_plotly_update(fig_coef, channel_index, xtime_shifted, y_data)
                        # Peak marker trace is trace 6 in col=1
                        safe_plotly_update(fig_coef, 6, all_peak_x, all_peak_y)
                        # Frequency Coef (all sub-bands) is trace 7 in col=2
                        x1 = []
                        y1 = []
                        for i in range(num_of_subband):
                            if len(freq[1][i]) == len(data[1][i]) and freq[1][i]:
                                x1 += freq[1][i]
                                y1 += data[1][i]
                        safe_plotly_update(fig_coef, 7, x1, y1)

                    if plot_psd_window:
                        trace_offset = 0
                        if plot_cancellation_depth:
                            # Cancellation Depth
                            x3 = []
                            y3 = []
                            for i in range(num_of_subband):
                                if len(freq[3][i]) == len(data[3][i]) and freq[3][i]:
                                    x3 += freq[3][i]
                                    y3 += data[3][i]
                            safe_plotly_update(fig_psd, 0, x3, y3)
                            trace_offset = 1
                        # Echo PSD
                        x5 = []
                        y5 = []
                        for i in range(num_of_subband):
                            if len(freq[5][i]) == len(data[5][i]) and freq[5][i]:
                                x5 += freq[5][i]
                                y5 += data[5][i]
                        safe_plotly_update(fig_psd, trace_offset + 0, x5, y5)
                        # Residual Echo PSD
                        x6 = []
                        y6 = []
                        for i in range(num_of_subband):
                            if len(freq[6][i]) == len(data[6][i]) and freq[6][i]:
                                x6 += freq[6][i]
                                y6 += data[6][i]
                        safe_plotly_update(fig_psd, trace_offset + 1, x6, y6)
                        # Downstream PSD
                        x7 = []
                        y7 = []
                        for i in range(num_of_subband):
                            if len(freq[7][i]) == len(data[7][i]) and freq[7][i]:
                                x7 += freq[7][i]
                                y7 += data[7][i]
                        safe_plotly_update(fig_psd, trace_offset + 2, x7, y7)
                        # Upstream PSD
                        x8 = []
                        y8 = []
                        for i in range(num_of_subband):
                            if len(freq[8][i]) == len(data[8][i]) and freq[8][i]:
                                x8 += freq[8][i]
                                y8 += data[8][i]
                        safe_plotly_update(fig_psd, trace_offset + 3, x8, y8)
                        # RL and RxSNR traces if enabled
                        if plot_rl_trace:
                            y9 = [(a - b) * -1 for a, b in zip(y7, y5)] if (y7 and y5 and len(y7) == len(y5)) else []
                            safe_plotly_update(fig_psd, trace_offset + 4, x7, y9)
                        if plot_rxsnr_trace:
                            y10 = [(a - b) for a, b in zip(y8, y6)] if (y8 and y6 and len(y8) == len(y6)) else []
                            safe_plotly_update(fig_psd, trace_offset + 5, x8, y10)

                    # --- Save HTML after each .dat file collection ---
                    if fig_coef: fig_coef.write_html(f"{path}/EC_Coefficients{identifier_suffix}.html")
                    if fig_psd: fig_psd.write_html(f"{path}/EC_PSD_Metrics{identifier_suffix}.html")
                    # --- Save JSON for live Dash viewing ---
                    if fig_coef: fig_coef.write_json(f"{path}/EC_Coefficients{identifier_suffix}.json")
                    if fig_psd: fig_psd.write_json(f"{path}/EC_PSD_Metrics{identifier_suffix}.json")
                    # --- End HTML/JSON save ---

                else:
                    # This block runs if the command validation fails
                    print(f"Command '{command}' FAILED or did not return expected output.")
                    print("--- Command Output (last 10 lines) ---")
                    for line in command_output.splitlines()[-10:]:
                        print(line)
                    print("--------------------------------------")
                    print(f"Skipping processing for {filename}.")
                    continue

        print("\n--- Cycle complete. Saving final plots and CSVs. ---")
        # Save plots as HTML using Plotly
        if fig_coef: fig_coef.write_html(f"{path}/EC_Coefficients{identifier_suffix}.html")
        if fig_psd: fig_psd.write_html(f"{path}/EC_PSD_Metrics{identifier_suffix}.html")
        print("Plots saved.")

        # Optionally, display the plots in the browser (uncomment if desired)
        #if fig_coef: pio.show(fig_coef)
        #if fig_psd: pio.show(fig_psd)

        x1 = freq[1][0] + freq[1][1] + freq[1][2]; y1 = data[1][0] + data[1][1] + data[1][2]
        x3 = freq[3][0] + freq[3][1] + freq[3][2]; y3 = data[3][0] + data[3][1] + data[3][2]
        x5 = freq[5][0] + freq[5][1] + freq[5][2]; y5 = data[5][0] + data[5][1] + data[5][2]
        x6 = freq[6][0] + freq[6][1] + freq[6][2]; y6 = data[6][0] + data[6][1] + data[6][2]
        x7 = freq[7][0] + freq[7][1] + freq[7][2]; y7 = data[7][0] + data[7][1] + data[7][2]
        x8 = freq[8][0] + freq[8][1] + freq[8][2]; y8 = data[8][0] + data[8][1] + data[8][2]
        y9 = [(a - b) * -1 for a, b in zip(y7, y5)] if (y7 and y5 and len(y7) == len(y5)) else []
        y10 = [(a - b) for a, b in zip(y8, y6)] if (y8 and y6 and len(y8) == len(y6)) else []

        save_trace_to_csv(f'{path}/FreqCoef{identifier_suffix}.csv', ["Frequency(MHz)", "Magnitude(dB)"], x1, y1, run_single)
        # Only save cancellation depth CSV if enabled
        if plot_cancellation_depth:
            save_trace_to_csv(f'{path}/Cancellation_Depth{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dB)"], x3, y3, run_single)
        save_trace_to_csv(f'{path}/Echo_PSD{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dBmV/100kHz)"], x5, y5, run_single)
        save_trace_to_csv(f'{path}/Residual_Echo_PSD{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dBmV/100kHz)"], x6, y6, run_single)
        save_trace_to_csv(f'{path}/Downstream_PSD{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dBmV/100kHz)"], x7, y7, run_single)
        save_trace_to_csv(f'{path}/Upstream_PSD{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dBmV/100kHz)"], x8, y8, run_single)
        if plot_rl_trace: save_trace_to_csv(f'{path}/Return_Loss{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dB)"], x7, y9, run_single)
        if plot_rxsnr_trace: save_trace_to_csv(f'{path}/Upstream_Rx_SNR{identifier_suffix}.csv', ["Frequency(MHz)", "Power(dB)"], x8, y10, run_single)

        # --- Replace this block ---
        # all_channels_x_data = {}
        # all_channels_y_data = {}
        # plot_lines = [line20, line21, line22, line23, line24, line25]
        # for i, line in enumerate(plot_lines):
        #     x_data, y_data = line.get_data()
        #     if len(y_data) > 0:
        #         all_channels_x_data[i] = x_data
        #         all_channels_y_data[i] = y_data

        # --- With this Plotly-based extraction ---
        all_channels_x_data = {}
        all_channels_y_data = {}
        # In fig_coef, traces 1-6 are the time coef channels ch0-ch5
        if fig_coef:
            for i in range(6):
                trace = fig_coef.data[1 + i]
                x_data = list(trace.x) if trace.x is not None else []
                y_data = list(trace.y) if trace.y is not None else []
                if len(y_data) > 0:
                    all_channels_x_data[i] = x_data
                    all_channels_y_data[i] = y_data

        time_coef_filepath = f'{path}/TimeCoef_IFFT_per_channel{identifier_suffix}_{args.time_axis}.csv'
        file_exists = os.path.exists(time_coef_filepath)
        timestamp = time.strftime('%Y%m%d_%H%M%S')

        if run_single or not file_exists:
            csv_header = []
            if args.time_axis == 'distance':
                csv_header.append("Distance(ft)")
            else:
                csv_header.append("Time(us)")

            for i in range(6):
                csv_header.append(f"ch{i}_dB_{timestamp}")

            max_len = max(len(d) for d in all_channels_y_data.values()) if all_channels_y_data else 0

            ref_x_data = []
            if all_channels_x_data:
                ref_channel_index = max(all_channels_x_data, key=lambda k: len(all_channels_x_data[k]))
                ref_x_data = all_channels_x_data[ref_channel_index]

            csv_data_columns = []
            csv_data_columns.append(list(ref_x_data) + [''] * (max_len - len(ref_x_data)))

            for i in range(6):
                y_data = all_channels_y_data.get(i, [])
                csv_data_columns.append(list(y_data) + [''] * (max_len - len(y_data)))

            with open(time_coef_filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(csv_header)
                rows = zip_longest(*csv_data_columns, fillvalue='')
                writer.writerows(rows)
        else:
            try:
                with open(time_coef_filepath, 'r', newline='') as f:
                    reader = csv.reader(f)
                    existing_rows = list(reader)

                if not existing_rows:
                    print(f"Warning: {time_coef_filepath} exists but is empty. Overwriting.")
                    pass
                else:
                    for i in range(6):
                        existing_rows[0].append(f"ch{i}_dB_{timestamp}")

                    max_new_rows = max(len(d) for d in all_channels_y_data.values()) if all_channels_y_data else 0

                    while len(existing_rows) -1 < max_new_rows:
                         existing_rows.append([''] * len(existing_rows[0]))

                    for ch_idx in range(6):
                        y_data_for_ch = all_channels_y_data.get(ch_idx, [])
                        for i in range(max_new_rows):
                             new_value = y_data_for_ch[i] if i < len(y_data_for_ch) else ''
                             existing_rows[i+1].append(new_value)

                    with open(time_coef_filepath, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerows(existing_rows)
            except Exception as e:
                print(f"Error updating Time Coef CSV {time_coef_filepath}: {e}")

        print("All CSVs saved.")

        # --- Show plots after each data cycle ---
        # Use auto_open=False to avoid opening new browser tabs/windows each time
        if fig_coef: pio.show(fig_coef, auto_open=False)
        if fig_psd: pio.show(fig_psd, auto_open=False)

        if run_single: 
            print("Single run complete.")
            # Show plots at end of single run (already shown above)
            break

    except Exception as e:
        print(f"An unexpected error occurred: {e}"); import traceback; traceback.print_exc(); break
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected. Exiting."); break

print("Closing connections...")
if 'target_client' in locals() and target_client.get_transport().is_active(): target_client.close()
if not args.no_jump and 'jumpbox_client' in locals() and jumpbox_client.get_transport().is_active(): jumpbox_client.close()
if 'target_scp_client' in locals(): target_scp_client.close()
if not run_single: time.sleep(1)

print("Script finished.")
if not run_single:
    print("Press Ctrl+C in the console to exit.")
    # Show plots at end of continuous mode
    if fig_coef: pio.show(fig_coef)
    if fig_psd: pio.show(fig_psd)
