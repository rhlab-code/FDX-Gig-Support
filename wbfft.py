### WBFFT Combined Analyzer
# v2.0.3: Fixed a bug where filenames would use the MAC address even when an IP was provided.
#         Filenames now use the IP as the identifier if the --ip flag is used.
# v2.0.2: Added --ip, --mac, and --domain command-line arguments to override config values.
# v2.0.1: change the y-axis from Amplitude (dBmV) to Power (dBmV/100kHz)
# v2.0.0: Refactored to use a unified config manager and amp library,
#         removing the need for multiple config_xxx.py and amp3_xxx.py files.
#
# Previous versions included:
# v1.8.0: Added --no-jump flag for direct connections and ensured MAC is in all output filenames.
# v1.7.0: save filename with mac
# v1.6.x: Various bug fixes and feature enhancements.
# v2.0.4: Intial github respository with interactive HTML plots.
# v2.0.5: cleanup

''' example usages:
python wbfft.py --image CC --domain PROD --channels '99M-1215M(6M)' --mac '24:a1:86:00:41:74'
python wbfft.py --image CC --domain PROD --channels '650(1150M)' --mac 24:a1:86:00:41:74
--channels '650(1150M)'  will provide the TCP including OOB signal@104.2MHz
python .\wbfft.py --image CC --domain PROD --channels '99M-1215M(6M)' --ip 2001:0558:6027:0072:D8B4:47CC:CB8A:CFF9
'''

import webbrowser
import paramiko
import sys
import os
import csv
import re
import time
import ipaddress
import argparse
import pandas as pd
import numpy as np
import logging
import math
import subprocess
from paramiko import SSHClient
from scp import SCPClient
from itertools import zip_longest

# New unified library imports
import config_manager
import wbfft_amp_library

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="FDX-AMP WBFFT Analyzer for multiple measurement points.")
parser.add_argument('--image', type=str, choices=['CS', 'CC', 'SC'], required=True,
                    help='Specify the image type: CS (CommScope), CC (Comcast), or SC (Sercomm).')
parser.add_argument('--measurement', nargs='+', default=['north_port_input', 'south_port_output', 'ds_afe_input'],
                    choices=['north_port_input', 'south_port_output', 'ds_afe_input'],
                    help='Select one or more measurements to perform.')
parser.add_argument('--path', type=str, help="Optional. Path for output files. Overrides the value in config.")
parser.add_argument('--channels', default=None,
                    help="Optional. String defining channels for power calculation. Ex: '111M-123M(6M),150M(6M)'")
parser.add_argument('--note', help="Optional note to append to all output filenames.")
parser.add_argument('--no-jump', action='store_true',
                    help='Skip the jump server and connect directly to the target device.')
# --- New arguments added ---
parser.add_argument('--mac', type=str, help="Optional. Target device MAC address. Overrides the value in config.")
parser.add_argument('--ip', type=str, help="Optional. Target device IP address. Overrides the value in config and any MAC-based IP lookup.")
parser.add_argument('--domain', type=str, help="Optional. CM domain for IP lookup script. Overrides the value in config.")

args = parser.parse_args()

# --- Configuration ---
try:
    import plotly.graph_objects as go
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def run_script_and_get_result(script_path, arguments=[]):
  """Runs a Python script in a subprocess and returns the output."""
  try:
    command = ["python", script_path] + arguments
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode == 0:
      return process.stdout.strip()
    else:
      print(f"Error running script: {process.stderr}")
      return None
  except FileNotFoundError:
    print(f"Script not found: {script_path}")
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

def parse_hal_gains(filepath, section_marker, gain_names):
    """Generic function to parse gain values from a HAL status file."""
    gains = {name: None for name in gain_names}
    in_target_section = False
    gain_pattern = re.compile(r'\(([^d]+)dB\)')
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if section_marker in line:
                    in_target_section = True
                    continue

                if in_target_section:
                    for name in gain_names:
                        if name in line:
                            match = gain_pattern.search(line)
                            if match:
                                gains[name] = float(match.group(1))

                    if "lafe_show_status" in line or "fafe_show_status" in line:
                        if section_marker not in line:
                            in_target_section = False

        for name, value in gains.items():
            if value is None:
                logging.error(f"Could not find {name} under '{section_marker}'.")
                return None
            logging.info(f"Found {name}: {value:.2f} dB")
        return gains
    except FileNotFoundError:
        logging.error(f"HAL file not found: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Error reading HAL file {filepath}: {e}")
        return None

def parse_wbfft_data(filepath):
    """Parses the WBFFT text file."""
    data = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if ":" in line and (parts := line.strip().split(':')) and len(parts) == 2:
                    try:
                        data.append({'Frequency': float(parts[0]), 'Amplitude': float(parts[1])})
                    except ValueError:
                        continue
        if not data:
            logging.error(f"No valid data in WBFFT file: {filepath}")
            return None
        logging.info(f"Parsed {len(data)} points from WBFFT file.")
        return pd.DataFrame(data)
    except FileNotFoundError:
        logging.error(f"WBFFT file not found: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Error reading WBFFT file {filepath}: {e}")
        return None

def parse_s21_data(filepath):
    """
    Parses S21 data from multiple file formats (Touchstone .s2p, FSW .txt, WBFFT .txt).
    It auto-detects the format and extracts frequency and magnitude data.
    """
    frequencies, s21_magnitudes = [], []
    file_format = None

    try:
        with open(filepath, 'r') as f:
            # --- Format Detection ---
            first_line = f.readline().strip()
            if 'Type;FSW-8;' in first_line or (';' in first_line and len(first_line.split(';')) > 1):
                file_format = 'fsw_txt'
                logging.info(f"Detected FSW .txt format for {filepath}")
            elif 'Received' in first_line and 'bins' in first_line:
                file_format = 'wbfft_txt'
                logging.info(f"Detected WBFFT .txt format for {filepath}")
            else:
                file_format = 's2p'
                logging.info(f"Assuming Touchstone .s2p format for {filepath}")

            f.seek(0) # Reset file pointer to the beginning

            # --- Parsing Logic based on Format ---
            if file_format == 's2p':
                data_started = False
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('!'): continue
                    if line.startswith('#'): data_started = True; continue
                    if data_started and (parts := line.split()) and len(parts) >= 4:
                        try:
                            frequencies.append(float(parts[0]))
                            s21_magnitudes.append(float(parts[3]))
                        except (ValueError, IndexError):
                            logging.warning(f"Skipping malformed data line in {filepath}: {line}")

            elif file_format == 'fsw_txt':
                data_started = False
                for line in f:
                    line = line.strip()
                    if 'Values;' in line:
                        data_started = True
                        continue
                    if data_started:
                        parts = line.split(';')
                        if len(parts) >= 2:
                            try:
                                frequencies.append(float(parts[0]))
                                s21_magnitudes.append(float(parts[1]))
                            except ValueError:
                                logging.warning(f"Skipping malformed data line in {filepath}: {line}")

            elif file_format == 'wbfft_txt':
                for line in f:
                    if ":" in line and (parts := line.strip().split(':')) and len(parts) == 2:
                        try:
                            frequencies.append(float(parts[0]))
                            s21_magnitudes.append(float(parts[1]))
                        except ValueError:
                            continue

        if not frequencies:
            logging.error(f"No valid data points parsed from file: {filepath}")
            return None

        logging.info(f"Parsed {len(frequencies)} points from {filepath}.")
        return pd.DataFrame({'Frequency': frequencies, 'S21_Magnitude': s21_magnitudes})

    except FileNotFoundError:
        logging.error(f"S-parameter/calibration file not found: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Error reading S-parameter/calibration file {filepath}: {e}")
        return None

def parse_freq_string(s):
    """Converts a frequency string like '111M' or '6k' to float in Hz."""
    s = s.strip().upper()
    multiplier = 1
    if s.endswith('G'): multiplier = 1e9; s = s[:-1]
    elif s.endswith('M'): multiplier = 1e6; s = s[:-1]
    elif s.endswith('K'): multiplier = 1e3; s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        logging.error(f"Could not parse frequency value: {s}")
        return None

def parse_channel_definitions(channels_str):
    """Parses a complex channel definition string into a list of channels."""
    if not channels_str: return []
    final_channels = []
    range_pattern = re.compile(r"([\d\.]+[KMG]?)-([\d\.]+[KMG]?)\(([\d\.]+[KMG]?)\)")
    single_pattern = re.compile(r"([\d\.]+[KMG]?)\(([\d\.]+[KMG]?)\)")
    for definition in channels_str.split(','):
        definition = definition.strip()
        if match := range_pattern.match(definition):
            start_hz, stop_hz, step_hz = map(parse_freq_string, match.groups())
            if any(v is None for v in [start_hz, stop_hz, step_hz]): continue
            current_cf = start_hz
            while current_cf <= stop_hz:
                final_channels.append({'cf_hz': current_cf, 'bw_hz': step_hz})
                current_cf += step_hz
        elif match := single_pattern.match(definition):
            cf_hz, bw_hz = map(parse_freq_string, match.groups())
            if cf_hz is not None and bw_hz is not None:
                final_channels.append({'cf_hz': cf_hz, 'bw_hz': bw_hz})
        else:
            logging.warning(f"Could not parse channel definition: '{definition}'")
    return final_channels

def calculate_channel_power(df, channels_to_calculate, power_column_name):
    """Calculates power for specified channels from the results DataFrame."""
    power_results = []
    if df.empty:
        logging.error("Input DataFrame is empty, cannot calculate channel power.")
        return power_results
    for channel in channels_to_calculate:
        cf_hz, bw_hz = channel['cf_hz'], channel['bw_hz']
        start_freq, end_freq = cf_hz - (bw_hz / 2.0), cf_hz + (bw_hz / 2.0)
        channel_df = df[(df['Frequency'] >= start_freq) & (df['Frequency'] < end_freq)]
        if channel_df.empty:
            power_dBmV = -math.inf
        else:
            linear_power = 10**(channel_df[power_column_name] / 10)
            total_linear_power = linear_power.sum()
            power_dBmV = 10 * math.log10(total_linear_power) if total_linear_power > 0 else -math.inf
        power_results.append({
            'CenterFrequency_MHz': f"{cf_hz/1e6:.3f}", 'Bandwidth_MHz': f"{bw_hz/1e6:.3f}", 'Channel_Power_dBmV': f"{power_dBmV:.2f}"
        })
    return power_results

# --- Main Logic ---
def main():
    # Load configuration based on --image flag
    config = config_manager.CONFIGURATIONS[args.image]

    # Instantiate the correct amplifier control class
    if args.image == 'CS':
        amp = wbfft_amp_library.CommscopeAmp()
    elif args.image == 'CC':
        amp = wbfft_amp_library.ComcastAmp()
    elif args.image == 'SC':
        amp = wbfft_amp_library.SercommAmp()
    else:
        logging.error(f"Invalid image type '{args.image}' provided.")
        sys.exit(1)

    # --- Modified Section: Override config with command-line arguments ---
    # Extract config variables, which will serve as defaults
    target_hostname = config['target_hostname']
    target_cm_mac = config['target_ecm_mac']
    cm_domain = config['cm_domain']
    # path = config['result_path']
    path = "./output/" +args.path+"/wbfft" # Use command-line path if provided
    appendix = config['result_filename_appendix']

    # Override config with command-line arguments if provided
    if args.mac:
        target_cm_mac = args.mac
        logging.info(f"Using MAC address from command line: {target_cm_mac}")

    if args.domain:
        cm_domain = args.domain
        logging.info(f"Using CM domain from command line: {cm_domain}")

    # IP address from --ip flag has the highest priority.
    # If not provided, try to find IP from MAC.
    # If that fails, fall back to the hostname from the config.
    if args.ip:
        target_hostname = args.ip
        logging.info(f"Using IP address from command line: {target_hostname}")
    elif target_cm_mac:
        logging.info(f"Looking up IP for MAC: {target_cm_mac}")
        script = os.path.join(config['get_ip_path'], config['get_ip_script'])
        arguments = [cm_domain, "CPE", target_cm_mac] # Use the potentially overridden domain
        temp = run_script_and_get_result(script, arguments)
        if temp and (is_ipv4(temp) or is_ipv6(temp)):
            target_hostname = temp
            logging.info(f"Found IP: {target_hostname}")
        else:
            logging.warning(f"Could not find a valid IP for MAC {target_cm_mac}. Will use hostname from config: {target_hostname}")
    # --- End of Modified Section ---

    s2p_remote_path = config.get('s2p_remote_path', '/run/data/calibration/')
    s2p_filenames = config.get('s2p_filenames', {})
    additional_comp_remote_path = config.get('additional_comp_remote_path', '/tmp/')
    additional_comp_filenames = config.get('additional_comp_filenames', {})

    if args.note:
        sanitized_note = re.sub(r'[\\/*?:"<>|]', '_', args.note)
        appendix += f"_{sanitized_note}"

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
    # --- End of BUG FIX ---

    os.makedirs(path, exist_ok=True)

    measurement_configs = {
        'north_port_input': {
            'adcSelect': 'ADC_NPU', 'rfboard_commands': config['rfboard_commands'],
            'hal_commands': config['hal_commands'],
            'hal_gain_section': 'lafe_show_status 0', 'hal_gain_names': ('PreAdcRxGain', 'PostAdcRxGain'),
            's2p_keys': {'H21': 'subtract'},
            'add_comp_keys': {},
            'output_prefix': 'North_Port_Input'
        },
        'south_port_output': {
            'adcSelect': 'ADC_DP0', 'rfboard_commands': config['rfboard_commands'],
            'hal_commands': config['hal_commands'],
            'hal_gain_section': 'lafe_show_status 4', 'hal_gain_names': ('PreAdcRxGain', 'PostAdcRxGain'),
            's2p_keys': {'H35': 'subtract', 'H65': 'add'},
            'add_comp_keys': {'SP_DTS_OUT': 'add', 'SF_WBFFT_ADC': 'subtract'},
            'output_prefix': 'South_Port_Output'
        },
        'ds_afe_input': {
            'adcSelect': 'ADC_NPD', 'rfboard_commands': config['rfboard_commands'],
            'hal_commands': config['hal_commands'],
            'hal_gain_section': 'fafe_show_status 4', 'hal_gain_names': ('PreAdcNcGain', 'PostAdcNcGain'),
            's2p_keys': {},
            'add_comp_keys': {},
            'output_prefix': 'DS_AFE_Input'
        }
    }

    processed_data_frames = []
    all_power_results = []

    jumpbox_client, target_client, channel = None, None, None
    try:
        # --- SSH Connection Logic ---
        if not args.no_jump:
            logging.info("Connecting to jumpbox and target device...")
            jumpbox_client = paramiko.SSHClient(); jumpbox_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            jumpbox_client.connect(config['jumpbox_hostname'], username=config['jumpbox_username'])
            transport = jumpbox_client.get_transport()
            dest_addr = (target_hostname, 22)
            jumpbox_channel = transport.open_channel("direct-tcpip", dest_addr, ('', 0))
            target_client = paramiko.SSHClient(); target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            target_client.connect(target_hostname, username=config['target_username'], password=config['target_password'], sock=jumpbox_channel)
        else:
            logging.info("Connecting directly to target device...")
            target_client = paramiko.SSHClient(); target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            target_client.connect(target_hostname, username=config['target_username'], password=config['target_password'])

        channel = target_client.invoke_shell(); channel.settimeout(1000)
        target_scp_client = SCPClient(target_client.get_transport())
        logging.info("SSH connection established.")

        # --- Stage 1: Run unique remote commands ---
        logging.info("--- Stage 1: Running unique remote commands ---")
        all_rfboard_cmds = set(cmd for m_name in args.measurement for cmd in measurement_configs[m_name]['rfboard_commands'])
        all_hal_cmds = set(cmd for m_name in args.measurement for cmd in measurement_configs[m_name]['hal_commands'])

        consolidated_rfboard_file = os.path.join(path, f"rfboard_all{identifier_suffix}{appendix}.txt")
        consolidated_hal_file = os.path.join(path, f"hal_all{identifier_suffix}{appendix}.txt")

        if all_rfboard_cmds:
            logging.info(f"Running RFboard commands: {list(all_rfboard_cmds)}")
            ret = "".join(amp.rf_comm(channel, cmd) for cmd in all_rfboard_cmds)
            with open(consolidated_rfboard_file, 'w') as f:
                f.write('\n'.join(line.strip() for line in ret.splitlines() if line.strip()))

        if all_hal_cmds:
            logging.info(f"Running HAL commands: {list(all_hal_cmds)}")
            ret = "".join(amp.hal_comm(channel, cmd, "InputPower") for cmd in all_hal_cmds)
            with open(consolidated_hal_file, 'w') as f:
                f.write('\n'.join(line.strip() for line in ret.splitlines() if line.strip()))

        # --- Stage 2: Run WBFFT captures and gather file list ---
        logging.info("--- Stage 2: Running WBFFT captures & building file list ---")
        remote_files_to_get = {}
        local_wbfft_paths = {}

        for measurement_name in args.measurement:
            m_config = measurement_configs[measurement_name]
            wbfft_config_cmd = f"/wbfft/configuration startFreq {config['startFreq']} endFreq {config['endFreq']} outputFormat {config['outputFormat']} fftSize {config['fftSize']} windowMode {config['windowMode']} averagingMode {config['averagingMode']} samplingRate {config['samplingRate']} adcSelect {m_config['adcSelect']} runDuration {config['runDuration']} triggerCount {config['triggerCount']} aggrPeriod {config['aggrPeriod']}"
            amp.hal_comm(channel, wbfft_config_cmd, "Success.")
            remote_wbfft_base = f"/tmp/WBFFT_{measurement_name}"
            amp.hal_comm(channel, f"/wbfft/start_capture 0 {remote_wbfft_base}", "Success.")
            time.sleep(1)

            local_wbfft_base = os.path.join(path, f"WBFFT_{m_config['output_prefix']}")
            local_wbfft_paths[measurement_name] = local_wbfft_base
            remote_files_to_get[remote_wbfft_base] = local_wbfft_base
            remote_files_to_get[f"{remote_wbfft_base}.config"] = f"{local_wbfft_base}.config"

        all_s2p_keys = set(key for m_name in args.measurement for key in measurement_configs[m_name]['s2p_keys'])
        for s2p_key in all_s2p_keys:
            s2p_file_with_path = s2p_filenames.get(s2p_key)
            if not s2p_file_with_path:
                logging.warning(f"S2P key '{s2p_key}' not found in config.s2p_filenames. Skipping.")
                continue
            full_remote_path = os.path.join(s2p_remote_path, s2p_file_with_path).replace("\\", "/")
            local_filename = os.path.basename(s2p_file_with_path)
            remote_files_to_get[full_remote_path] = os.path.join(path, local_filename)

        all_add_comp_keys = set(key for m_name in args.measurement for key in measurement_configs[m_name].get('add_comp_keys', {}))
        for comp_key in all_add_comp_keys:
            comp_file_with_path = additional_comp_filenames.get(comp_key)
            if not comp_file_with_path:
                logging.warning(f"Additional compensation key '{comp_key}' not found in config.additional_comp_filenames. Skipping.")
                continue
            full_remote_path = os.path.join(additional_comp_remote_path, comp_file_with_path).replace("\\", "/")
            local_filename = os.path.basename(comp_file_with_path)
            remote_files_to_get[full_remote_path] = os.path.join(path, local_filename)

        # --- Stage 3: Download all unique files ---
        logging.info("--- Stage 3: Downloading all required files ---")
        for remote, local in remote_files_to_get.items():
            try:
                logging.info(f"Downloading {remote} to {local}")
                target_scp_client.get(remote, local)
            except Exception as e:
                logging.error(f"Failed to download {remote}: {e}")
        logging.info("All downloads complete.")

        # --- Stage 4: Post-process each measurement ---
        logging.info("--- Stage 4: Post-processing all measurements ---")
        for measurement_name in args.measurement:
            logging.info(f"--- Processing: {measurement_name} ---")
            m_config = measurement_configs[measurement_name]

            wbfft_df = parse_wbfft_data(local_wbfft_paths[measurement_name])
            gains = parse_hal_gains(consolidated_hal_file, m_config['hal_gain_section'], m_config['hal_gain_names'])

            if wbfft_df is None or gains is None:
                logging.error(f"Cannot process {measurement_name} due to missing data.")
                continue

            result_series = wbfft_df['Amplitude'].copy() + 59.5

            for s2p_key, operation in m_config['s2p_keys'].items():
                s2p_file_with_path = s2p_filenames.get(s2p_key)
                if not s2p_file_with_path: continue
                local_filename = os.path.basename(s2p_file_with_path)
                local_s2p_path = os.path.join(path, local_filename)
                s21_df = parse_s21_data(local_s2p_path)
                if s21_df is not None:
                    s21_df = s21_df.sort_values(by='Frequency')
                    interpolated_s21_mag = np.interp(wbfft_df['Frequency'], s21_df['Frequency'], s21_df['S21_Magnitude'])
                    if operation == 'subtract': result_series -= interpolated_s21_mag
                    elif operation == 'add': result_series += interpolated_s21_mag

            for comp_key, operation in m_config.get('add_comp_keys', {}).items():
                comp_file_with_path = additional_comp_filenames.get(comp_key)
                if not comp_file_with_path: continue
                local_filename = os.path.basename(comp_file_with_path)
                local_comp_path = os.path.join(path, local_filename)
                comp_df = parse_s21_data(local_comp_path)
                if comp_df is not None:
                    comp_df = comp_df.sort_values(by='Frequency')
                    interpolated_comp_mag = np.interp(wbfft_df['Frequency'], comp_df['Frequency'], comp_df['S21_Magnitude'])
                    if operation == 'subtract': result_series -= interpolated_comp_mag
                    elif operation == 'add': result_series += interpolated_comp_mag

            if measurement_name in ['north_port_input', 'south_port_output']:
                result_series -= gains.get('PreAdcRxGain', 0)
                result_series -= gains.get('PostAdcRxGain', 0)
            elif measurement_name == 'ds_afe_input':
                result_series -= gains.get('PreAdcNcGain', 0)
                result_series -= gains.get('PostAdcNcGain', 0)

            wbfft_df[m_config['output_prefix']] = result_series
            processed_data_frames.append(wbfft_df[['Frequency', m_config['output_prefix']]].copy())

            if args.channels:
                channels_to_process = parse_channel_definitions(args.channels)
                if channels_to_process:
                    power_results = calculate_channel_power(wbfft_df, channels_to_process, m_config['output_prefix'])
                    if power_results:
                        power_df = pd.DataFrame(power_results)
                        power_df = power_df.rename(columns={'Channel_Power_dBmV': f"{m_config['output_prefix']}_Power_dBmV"})
                        all_power_results.append(power_df)

        # --- Stage 5: Consolidate and save final results ---
        logging.info("--- Stage 5: Consolidating final results ---")
        if not processed_data_frames:
            logging.warning("No data was processed, skipping final file generation.")
        else:
            final_df = processed_data_frames[0]
            for i in range(1, len(processed_data_frames)):
                final_df = pd.merge(final_df, processed_data_frames[i], on='Frequency', how='outer')

            final_df = final_df.sort_values(by='Frequency').reset_index(drop=True)

            final_csv_path = os.path.join(path, f"WBFFT_Combined_Results{identifier_suffix}{appendix}.csv")
            final_df.to_csv(final_csv_path, index=False, float_format='%.4f')
            logging.info(f"Successfully saved combined data to {final_csv_path}")

            # --- Plotly Interactive Plot and HTML Save ---
            if PLOTLY_AVAILABLE:
                final_plot_path = os.path.join(path, f"WBFFT_Combined_Plot{identifier_suffix}{appendix}.html")
                fig = go.Figure()
                for df in processed_data_frames:
                    col_name = df.columns[1]
                    fig.add_trace(go.Scatter(
                        x=df['Frequency'] / 1e6,
                        y=df[col_name],
                        mode='lines',
                        name=col_name
                    ))
                fig.update_layout(
                    title=f'Combined WBFFT Measurements{identifier_suffix}',
                    xaxis_title='Frequency (MHz)',
                    yaxis_title='Power (dBmV/100kHz)',
                    template='plotly_white',
                    legend=dict(bordercolor="black", borderwidth=1),
                    margin=dict(l=60, r=60, t=80, b=60),
                    height=700,
                    width=1200,
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
                                width=4
                            ),
                            fillcolor='rgba(0,0,0,0)',
                            layer="below"
                        )
                    ]
                )
                pio.write_html(fig, final_plot_path)
                logging.info(f"Successfully saved interactive plot to {final_plot_path}")
                ## Open html file
                # Convert the absolute path to a URL format (using the file:// scheme)
                abs_path = os.path.abspath(final_plot_path)
                # print(f"{abs_path}")
                url = f"file://{abs_path}"
                webbrowser.open_new_tab(url)
            # --- End Plotly Section ---

            if all_power_results:
                final_power_df = all_power_results[0]
                for i in range(1, len(all_power_results)):
                    final_power_df = pd.merge(final_power_df, all_power_results[i], on=['CenterFrequency_MHz', 'Bandwidth_MHz'], how='outer')

                final_power_df['CF_sort_key'] = pd.to_numeric(final_power_df['CenterFrequency_MHz'])
                final_power_df = final_power_df.sort_values(by='CF_sort_key').drop(columns=['CF_sort_key'])

                final_power_csv_path = os.path.join(path, f"WBFFT_Combined_ChannelPower{identifier_suffix}{appendix}.csv")
                final_power_df.to_csv(final_power_csv_path, index=False, float_format='%.2f')
                logging.info(f"Successfully saved combined channel power data to {final_power_csv_path}")

    except Exception as e:
        logging.error(f"An error occurred during the process: {e}", exc_info=True)
    finally:
        logging.info("Closing connections...")
        if channel: channel.close()
        if target_client: target_client.close()
        if not args.no_jump and jumpbox_client: jumpbox_client.close()

if __name__ == "__main__":
    main()
