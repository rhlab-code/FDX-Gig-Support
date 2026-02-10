import re
import pandas as pd
import logging
import numpy as np

def parse_key_value_output(output_text, command_name):
    """Generic parser for commands that return 'Key: Value' pairs."""
    parsed_data = {}
    if not output_text:
        return parsed_data
    for line in output_text.splitlines():
        if ':' in line:
            parts = line.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip()
            value_parts = value.split()
            final_value = value_parts[0] if value_parts else ""
            if key and final_value and key.lower() != command_name.lower():
                parsed_data[key] = final_value
    return parsed_data

def parse_module_info(output_text):
    """Wrapper for the generic parser for 'showModuleInfo'."""
    return parse_key_value_output(output_text, 'showModuleInfo')

def parse_spectrum_config(output):
    """Parses all values from 'show configuration' in spectrum mode."""
    config = {}
    lines = output.splitlines()
    for line in lines:
        line = line.strip()
        subband_match = re.match(r'subBand Mode:(\d+)\s+"([^"]+)"', line)
        if subband_match:
            subband_index = subband_match.group(1)
            mode = subband_match.group(2)
            config[f'subband_{subband_index}_mode'] = mode
            continue
        parts = re.split(r'\s{2,}', line)
        if len(parts) >= 2:
            key = parts[0].strip().replace(' ', '_')
            value_part = parts[1].strip()
            numeric_value_match = re.match(r'([\d\.]+)', value_part)
            if numeric_value_match:
                value = numeric_value_match.group(1)
            else:
                value = value_part
            if key and value and not key.startswith('-') and 'configuration' not in key.lower():
                config[key] = value
    return config

def parse_ds_profile_config(output):
    """Parses all values from 'show configuration' in ds-profile mode."""
    config = {}
    steps = {}
    for line in output.splitlines():
        line = line.strip()
        step_match = re.match(r'step-index:(\d+)\s+([\w-]+)\s+([\d\.]+)', line)
        if step_match:
            index_str, key, value = step_match.groups()
            index = int(index_str)
            key = key.strip().replace('-', '_')
            if index not in steps:
                steps[index] = {'index': index}
            steps[index][key] = value
            continue
        parts = re.split(r'\s{2,}', line)
        if len(parts) >= 2:
            key = parts[0].strip()
            value_part = parts[1].strip()
            value_match = re.match(r'([\d\.]+|\w+)', value_part)
            if value_match:
                value = value_match.group(1)
            else:
                value = value_part
            if key and value and not key.startswith('-') and 'configuration' not in key.lower():
                config[key] = value
    if steps:
        config['steps'] = [steps[i] for i in sorted(steps.keys())]
    return config

def parse_us_profile_config(output):
    """Parses the output of 'show configuration' in us-profile mode."""
    config = {}
    match = re.search(r"rlsp\s+([\d\.]+)", output)
    if match:
        config['rlsp'] = match.group(1).strip()
    return config

def parse_ds_freq_override_config(output):
    """Parses 'show configuration' in the ds-freq-override sub-mode."""
    config = {}
    match = re.search(r"Status:\s+(\w+)", output)
    if match:
        config['status'] = match.group(1).strip()
    return config

def parse_backoff_config(output):
    """Parses the output of 'show configuration' in north-port mode."""
    config = {}
    match = re.search(r"backoff\s+([\d\.]+)", output)
    if match:
        config['backoff'] = match.group(1).strip()
    return config

def parse_rf_components_config(output):
    """Parses the output of 'show rf-components'."""
    config = {}
    lines = output.splitlines()
    for line in lines:
        match_port = re.match(r'^([\w-]+)\s+(\w+)\s+([\d\.]+)', line.strip())
        match_no_port = re.match(r'^([\w-]+)\s+([\d\.]+)', line.strip())
        if match_port:
            key, port, value = match_port.groups()
            config_key = f"{key.strip()} {port.strip()}"
            config[config_key] = value.strip()
        elif match_no_port:
            key, value = match_no_port.groups()
            config[key.strip()] = value.strip()
    return config

def parse_alignment_status(output):
    """Parses the output of 'show alignment-status'."""
    config = {}
    for line in output.splitlines():
        if ':' in line:
            parts = line.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip()
            if key and value:
                config[key] = value
    return config

def parse_alignment_adjustment(output_text, adjustment_type):
    """Parses EQ or Attenuation adjustment values from alignment command output."""
    if not output_text or not adjustment_type:
        return None
    
    pattern = None
    if adjustment_type == 'eq':
        pattern = re.compile(r'slope by\s*\"(-?[\d\.]+)\"')
    elif adjustment_type == 'atten':
        pattern = re.compile(r'\(PAD IN\).*?by\s*\"(-?[\d\.]+)\"')

    if pattern:
        match = pattern.search(output_text)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                logging.warning(f"Could not parse float from matched alignment value: {match.group(1)}")
                return None
    return None

def parse_afe_status(output):
    """Parses the output of fafe_show_status and lafe_show_status commands."""
    data = {}
    header_match = re.search(r'((?:FAFE|LAFE)\s(?:core|status: Core)\s?-?(\d+))', output, re.IGNORECASE)
    if not header_match:
        return {} 
    top_key_raw = header_match.group(1).replace('status:','').replace('  ', ' ')
    top_key = "_".join(top_key_raw.split()).replace('-', '_')
    data[top_key] = {}
    kv_matches = re.findall(r'^\s*([\w\s]+?)\s*=\s*(.*)', output, re.MULTILINE)
    current_data = data[top_key]
    for key, value in kv_matches:
        key = key.strip()
        value = value.strip()
        current_data[key] = value
    if top_key.startswith("FAFE"):
        rx_data = {k: v for k, v in current_data.items() if k.startswith('Rx')}
        nc_data = {k: v for k, v in current_data.items() if k.startswith('Nc')}
        if rx_data or nc_data:
            if rx_data:
                for k in list(current_data.keys()):
                    if k.startswith('Rx'):
                        del current_data[k]
                current_data['Rx'] = rx_data
            if nc_data:
                for k in list(current_data.keys()):
                    if k.startswith('Nc'):
                        del current_data[k]
                current_data['Nc'] = nc_data
    return data

def parse_s2p_data(filepath):
    """
    Parses S21 data from multiple file formats (Touchstone .s2p, FSW .txt, WBFFT .txt).
    It auto-detects the format and extracts frequency and magnitude data.
    """
    frequencies, s21_magnitudes = [], []
    file_format = None
    try:
        with open(filepath, 'r') as f:
            first_line = f.readline().strip()
            if 'Type;FSW-8;' in first_line or (';' in first_line and len(first_line.split(';')) > 1):
                file_format = 'fsw_txt'
            elif 'Received' in first_line and 'bins' in first_line:
                file_format = 'wbfft_txt'
            else:
                file_format = 's2p'
            f.seek(0)
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
                    if 'Values;' in line: data_started = True; continue
                    if data_started and (parts := line.split(';')) and len(parts) >= 2:
                        try:
                            frequencies.append(float(parts[0])); s21_magnitudes.append(float(parts[1]))
                        except ValueError: logging.warning(f"Skipping malformed data line in {filepath}: {line}")
            elif file_format == 'wbfft_txt':
                for line in f:
                    if ":" in line and (parts := line.strip().split(':')) and len(parts) == 2:
                        try:
                            frequencies.append(float(parts[0])); s21_magnitudes.append(float(parts[1]))
                        except ValueError: continue
        if not frequencies: return None
        return pd.DataFrame({'Frequency': frequencies, 'S21_Magnitude': s21_magnitudes})
    except FileNotFoundError:
        logging.error(f"S-parameter/calibration file not found: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Error reading S-parameter/calibration file {filepath}: {e}")
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
        return pd.DataFrame(data)
    except FileNotFoundError:
        logging.error(f"WBFFT file not found: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Error reading WBFFT file {filepath}: {e}")
        return None

def parse_hal_gains_from_output(raw_output, section_marker, gain_names):
    """Generic function to parse gain values from a HAL status raw output string."""
    gains = {name: None for name in gain_names}
    in_target_section = False
    gain_pattern = re.compile(r'\(([^d]+)dB\)')
    try:
        for line in raw_output.splitlines():
            if section_marker in line:
                in_target_section = True
                continue
            if in_target_section:
                for name in gain_names:
                    if name in line:
                        match = gain_pattern.search(line)
                        if match:
                            gains[name] = float(match.group(1))
                # Heuristic to find the end of the section
                if "lafe_show_status" in line or "fafe_show_status" in line:
                    if section_marker not in line:
                        in_target_section = False
        for name, value in gains.items():
            if value is None:
                logging.error(f"Could not find {name} under '{section_marker}'.")
                return None
        return gains
    except Exception as e:
        logging.error(f"Error parsing HAL gains: {e}")
        return None